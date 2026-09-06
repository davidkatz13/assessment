import asyncio
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.orm import Batch, BatchError
from app.services.batch_ingestion_service import BatchIngestionService
from app.services.batch_validation_service import BatchValidationService
from core.enums import BatchStatus
from core.exceptions import BatchConflictError

# --- test doubles -------------------------------------------------------------
# Hand-rolled fakes rather than a mocking framework: the point of injecting
# repositories via the constructor (per the coding standard) is exactly so the
# ingestion service's business logic -- the atomicity/idempotency rules -- can be
# tested without a real database or disk.


class FakeFileStorageRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[bytes, str]] = []

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def save(self, content: bytes, checksum: str) -> str:
        self.saved.append((content, checksum))
        return f"/fake/storage/{checksum}.json"


class FakeBatchRepository:
    def __init__(
        self,
        *,
        existing_batch: Batch | None = None,
        existing_external_ids: set[str] | None = None,
        conflict_on_commit: bool = False,
    ) -> None:
        self._existing_batch = existing_batch
        self._existing_external_ids = existing_external_ids or set()
        self._conflict_on_commit = conflict_on_commit
        self.reject_calls: list[dict[str, Any]] = []
        self.commit_calls: list[dict[str, Any]] = []

    def get_by_checksum(self, checksum: str) -> Batch | None:
        return self._existing_batch

    def get_existing_external_ids(self, external_ids: set[str]) -> set[str]:
        return self._existing_external_ids & external_ids

    def reject_batch(self, **kwargs: Any) -> Batch:
        self.reject_calls.append(kwargs)
        return _fake_batch(
            status=BatchStatus.REJECTED,
            claim_count=0,
            errors=kwargs["errors"],
            errors_truncated=kwargs.get("errors_truncated", False),
        )

    def commit_batch(self, **kwargs: Any) -> Batch:
        if self._conflict_on_commit:
            raise BatchConflictError("simulated unique-constraint race")
        self.commit_calls.append(kwargs)
        return _fake_batch(
            status=BatchStatus.COMMITTED, claim_count=len(kwargs["claims"])
        )


class FakeUploadFile:
    def __init__(
        self, filename: str, content: bytes, content_type: str = "application/json"
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._buffer = io.BytesIO(content)

    async def read(self, size: int) -> bytes:
        return self._buffer.read(size)


def _fake_batch(
    *,
    status: str,
    claim_count: int,
    errors: list[dict[str, Any]] | None = None,
    errors_truncated: bool = False,
) -> Batch:
    batch = Batch(
        id=uuid.uuid4(),
        original_filename="batch.json",
        content_type="application/json",
        size_bytes=1,
        checksum_sha256="fake-checksum",
        storage_path="/fake/storage/x.json",
        status=status,
        claim_count=claim_count,
        errors_truncated=errors_truncated,
        submitted_at=datetime.now(UTC),
    )
    batch.errors = [
        BatchError(
            row_index=e["row_index"],
            external_id=e["external_id"],
            field=e["field"],
            message=e["message"],
        )
        for e in (errors or [])
    ]
    return batch


def _claim(**overrides: Any) -> dict[str, Any]:
    base = {
        "external_id": "CLM-1",
        "claimant_name": "Jane Doe",
        "policy_number": "POL-1",
        "claim_type": "auto",
        "amount_cents": 1000,
        "received_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _content(*claims: dict[str, Any]) -> bytes:
    return json.dumps({"claims": list(claims)}).encode()


def _service(
    batch_repository: FakeBatchRepository, file_repository: FakeFileStorageRepository
) -> BatchIngestionService:
    return BatchIngestionService(
        BatchValidationService(max_claims_per_batch=5000),
        batch_repository,
        file_repository,
        max_upload_size_bytes=1024 * 1024,
        max_reported_errors=200,
    )


# --- main path ------------------------------------------------------------------


def test_valid_batch_is_committed_with_all_claims():
    batch_repository = FakeBatchRepository()
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=_content(_claim(external_id="CLM-1"), _claim(external_id="CLM-2")),
        filename="batch.json",
        content_type="application/json",
    )

    assert result.batch.status == BatchStatus.COMMITTED
    assert not result.conflicted
    assert len(batch_repository.commit_calls) == 1
    assert len(batch_repository.commit_calls[0]["claims"]) == 2
    assert batch_repository.reject_calls == []


# --- rollback / failure paths -----------------------------------------------------


def test_invalid_claim_rejects_the_whole_batch_without_committing_anything():
    batch_repository = FakeBatchRepository()
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=_content(
            _claim(external_id="CLM-1"), _claim(external_id="CLM-2", amount_cents=-1)
        ),
        filename="batch.json",
        content_type="application/json",
    )

    assert result.batch.status == BatchStatus.REJECTED
    assert batch_repository.commit_calls == []
    assert len(batch_repository.reject_calls) == 1
    assert any(
        e["field"] == "amount_cents" for e in batch_repository.reject_calls[0]["errors"]
    )


def test_duplicate_external_id_against_existing_claim_rejects_the_batch():
    batch_repository = FakeBatchRepository(existing_external_ids={"CLM-1"})
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=_content(_claim(external_id="CLM-1")),
        filename="batch.json",
        content_type="application/json",
    )

    assert result.batch.status == BatchStatus.REJECTED
    assert batch_repository.commit_calls == []
    assert batch_repository.reject_calls[0]["errors"][0]["field"] == "external_id"


def test_wrong_extension_is_reported_as_a_batch_level_error():
    batch_repository = FakeBatchRepository()
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=_content(_claim()), filename="batch.csv", content_type="text/csv"
    )

    assert result.batch.status == BatchStatus.REJECTED
    assert batch_repository.reject_calls[0]["errors"][0]["field"] == "file"


def test_malformed_json_is_rejected_with_a_parse_error():
    batch_repository = FakeBatchRepository()
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=b"not json {", filename="batch.json", content_type="application/json"
    )

    assert result.batch.status == BatchStatus.REJECTED
    assert batch_repository.commit_calls == []


def test_unanticipated_db_conflict_rejects_and_flags_conflicted():
    batch_repository = FakeBatchRepository(conflict_on_commit=True)
    result = _service(batch_repository, FakeFileStorageRepository()).ingest(
        content=_content(_claim()),
        filename="batch.json",
        content_type="application/json",
    )

    assert result.conflicted is True
    assert result.batch.status == BatchStatus.REJECTED
    assert len(batch_repository.reject_calls) == 1


# --- idempotency -------------------------------------------------------------


def test_resubmitting_identical_bytes_returns_the_existing_batch_without_reprocessing():
    existing = _fake_batch(status=BatchStatus.COMMITTED, claim_count=3)
    batch_repository = FakeBatchRepository(existing_batch=existing)
    file_repository = FakeFileStorageRepository()

    result = _service(batch_repository, file_repository).ingest(
        content=_content(_claim()),
        filename="batch.json",
        content_type="application/json",
    )

    assert result.batch is existing
    assert file_repository.saved == []
    assert batch_repository.commit_calls == []
    assert batch_repository.reject_calls == []


# --- upload size limit (ingest_from_upload) --------------------------------------


def test_upload_exceeding_size_limit_raises_before_reading_it_all():
    from core.exceptions import BatchTooLargeError

    batch_repository = FakeBatchRepository()
    service = BatchIngestionService(
        BatchValidationService(max_claims_per_batch=5000),
        batch_repository,
        FakeFileStorageRepository(),
        max_upload_size_bytes=10,
        max_reported_errors=200,
    )
    upload = FakeUploadFile("batch.json", _content(_claim()))

    try:
        asyncio.run(service.ingest_from_upload(upload))
        assert False, "expected BatchTooLargeError"
    except BatchTooLargeError:
        pass

    assert batch_repository.commit_calls == []
    assert batch_repository.reject_calls == []
