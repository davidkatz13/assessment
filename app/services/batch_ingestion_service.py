from dataclasses import dataclass
from typing import Any

from fastapi import UploadFile

from app.models.orm import Batch
from app.repositories.batch_repository import BatchRepository
from app.repositories.file_storage_repository import FileStorageRepository
from app.services.batch_validation_service import BatchValidationService
from core.exceptions import BatchConflictError, BatchParseError, BatchTooLargeError


@dataclass
class BatchIngestionResult:
    batch: Batch
    conflicted: bool = False


class BatchIngestionService:
    """Business logic for ingesting one batch. This is where the atomicity and
    idempotency rules actually live: read the upload under its size limit, parse,
    validate, check for duplicates, then persist exactly one outcome (committed or
    rejected) via the repositories -- never a partial one.
    """

    _READ_CHUNK_SIZE = 1024 * 1024

    def __init__(
        self,
        validation_service: BatchValidationService,
        batch_repository: BatchRepository,
        file_repository: FileStorageRepository,
        max_upload_size_bytes: int,
        max_reported_errors: int,
    ) -> None:
        self._validation_service = validation_service
        self._batch_repository = batch_repository
        self._file_repository = file_repository
        self._max_upload_size_bytes = max_upload_size_bytes
        self._max_reported_errors = max_reported_errors

    async def ingest_from_upload(self, file: UploadFile) -> BatchIngestionResult:
        content = await self._read_within_limit(file)
        return self.ingest(
            content=content,
            filename=file.filename or "",
            content_type=file.content_type or "",
        )

    async def _read_within_limit(self, file: UploadFile) -> bytes:
        """Stream the upload in chunks, aborting before the whole file is buffered if
        it exceeds the configured limit -- a giant upload should fail fast, not first
        get fully read into memory just to be rejected. Raises BatchTooLargeError
        rather than an HTTP-specific exception, since this is a service-layer concern;
        the API layer's global exception handler maps it to a 413.
        """
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await file.read(self._READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > self._max_upload_size_bytes:
                raise BatchTooLargeError(
                    f"file exceeds maximum size of {self._max_upload_size_bytes} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def ingest(
        self, *, content: bytes, filename: str, content_type: str
    ) -> BatchIngestionResult:
        checksum = self._file_repository.compute_checksum(content)

        existing = self._batch_repository.get_by_checksum(checksum)
        if existing is not None:
            return BatchIngestionResult(batch=existing)

        storage_path = self._file_repository.save(content, checksum)
        size_bytes = len(content)

        errors: list[dict[str, Any]] = []
        if not filename.lower().endswith(".json"):
            errors.append(_error(field="file", message="expected a .json file"))

        try:
            raw_claims = self._validation_service.parse_claims(content)
        except BatchParseError as exc:
            errors.append(_error(message=str(exc)))
            raw_claims = []

        result = self._validation_service.validate(raw_claims)
        errors.extend(result.errors)

        if not errors:
            existing_ids = self._batch_repository.get_existing_external_ids(
                set(result.external_id_to_row_index)
            )
            for external_id in existing_ids:
                errors.append(
                    _error(
                        row_index=result.external_id_to_row_index[external_id],
                        external_id=external_id,
                        field="external_id",
                        message="a claim with this external_id already exists",
                    )
                )

        if errors:
            truncated = len(errors) > self._max_reported_errors
            batch = self._batch_repository.reject_batch(
                original_filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                checksum=checksum,
                storage_path=storage_path,
                errors=errors[: self._max_reported_errors],
                errors_truncated=truncated,
            )
            return BatchIngestionResult(batch=batch)

        try:
            batch = self._batch_repository.commit_batch(
                original_filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                checksum=checksum,
                storage_path=storage_path,
                claims=result.valid_claims,
            )
        except BatchConflictError as exc:
            batch = self._batch_repository.reject_batch(
                original_filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                checksum=checksum,
                storage_path=storage_path,
                errors=[_error(message=f"could not commit batch: {exc}")],
            )
            return BatchIngestionResult(batch=batch, conflicted=True)

        return BatchIngestionResult(batch=batch)


def _error(
    *,
    row_index: int | None = None,
    external_id: str | None = None,
    field: str | None = None,
    message: str,
) -> dict[str, Any]:
    return {
        "row_index": row_index,
        "external_id": external_id,
        "field": field,
        "message": message,
    }
