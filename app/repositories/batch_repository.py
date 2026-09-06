import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.orm import Batch, BatchError, Claim
from core.enums import BatchStatus
from core.exceptions import BatchConflictError


class BatchRepository:
    """All DB reads/writes for batches, batch_errors, and claims, including the
    transaction boundaries that make batch ingestion atomic."""

    def __init__(self, session: Session) -> None:
        """Store the request-scoped session all methods below execute against."""
        self._session = session

    def get_by_checksum(self, checksum: str) -> Batch | None:
        """Return the batch previously stored under this file checksum, if any.

        Used for idempotent replay: a caller resubmitting byte-identical content
        gets back the original outcome instead of triggering reprocessing.
        """
        stmt = (
            select(Batch)
            .options(selectinload(Batch.errors))
            .where(Batch.checksum_sha256 == checksum)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_existing_external_ids(self, external_ids: set[str]) -> set[str]:
        """Return the subset of external_ids that already belong to a persisted claim."""
        if not external_ids:
            return set()
        stmt = select(Claim.external_id).where(Claim.external_id.in_(external_ids))
        return set(self._session.execute(stmt).scalars().all())

    def reject_batch(
        self,
        *,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        checksum: str,
        storage_path: str,
        errors: list[dict[str, Any]],
        errors_truncated: bool = False,
    ) -> Batch:
        """Persist a rejected batch attempt and its errors in one transaction. No
        claims are ever written on this path, so atomicity is trivial. The error list
        is capped by the caller (MAX_REPORTED_ERRORS), so a plain per-row loop here is
        fine -- it's the claims path that needs the bulk-insert treatment."""
        batch = Batch(
            id=uuid.uuid4(),
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            storage_path=storage_path,
            status=BatchStatus.REJECTED,
            claim_count=0,
            errors_truncated=errors_truncated,
        )
        self._session.add(batch)
        try:
            for error in errors:
                self._session.add(BatchError(batch_id=batch.id, **error))
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise BatchConflictError(str(exc.orig)) from exc
        return batch

    def commit_batch(
        self,
        *,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        checksum: str,
        storage_path: str,
        claims: list[dict[str, Any]],
    ) -> Batch:
        """Persist the batch and all of its claims in one transaction.

        Claims are written via a single Core `insert()` with a list of dicts rather
        than one `session.add(Claim(...))` per row: SQLAlchemy 2.0's insertmanyvalues
        turns that into a small number of multi-row INSERT statements (auto-chunked
        under the dialect's parameter limit) instead of paying per-instance ORM
        overhead for every claim, which matters once a batch has thousands of rows.
        Still one transaction, so atomicity is unaffected by how the rows are sent.

        If an unanticipated DB error surfaces here (e.g. a unique-constraint race on
        external_id), the whole transaction is rolled back and translated into a
        BatchConflictError for the service layer to handle.
        """
        batch_id = uuid.uuid4()
        batch = Batch(
            id=batch_id,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum,
            storage_path=storage_path,
            status=BatchStatus.COMMITTED,
            claim_count=len(claims),
        )
        self._session.add(batch)
        try:
            # The session has autoflush disabled, and the bulk insert() below is a
            # Core statement that bypasses the ORM unit-of-work entirely -- so without
            # an explicit flush here, the batches row is never sent to Postgres before
            # the claims insert runs, and the FK check fails against a batch_id that
            # doesn't exist yet.
            self._session.flush()
            if claims:
                rows = [
                    {**claim, "id": uuid.uuid4(), "batch_id": batch_id}
                    for claim in claims
                ]
                self._session.execute(insert(Claim), rows)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise BatchConflictError(str(exc.orig)) from exc
        return batch

    def list_batches(
        self,
        *,
        batch_id: uuid.UUID | None,
        status: str | None,
        submitted_after: datetime | None,
        submitted_before: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Batch], int]:
        """Return a page of batches matching the given filters, newest first, plus
        the total count matching those filters (independent of limit/offset)."""
        conditions = []
        if batch_id is not None:
            conditions.append(Batch.id == batch_id)
        if status is not None:
            conditions.append(Batch.status == status)
        if submitted_after is not None:
            conditions.append(Batch.submitted_at >= submitted_after)
        if submitted_before is not None:
            conditions.append(Batch.submitted_at <= submitted_before)

        total = self._session.execute(
            select(func.count()).select_from(Batch).where(*conditions)
        ).scalar_one()
        stmt = (
            select(Batch)
            .options(selectinload(Batch.errors))
            .where(*conditions)
            .order_by(Batch.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self._session.execute(stmt).scalars().all())
        return items, total

    def list_claims(
        self,
        *,
        policy_number: str | None,
        claimant_name: str | None,
        claim_type: str | None,
        status: str | None,
        batch_id: uuid.UUID | None,
        received_after: datetime | None,
        received_before: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Claim], int]:
        """Return a page of claims matching the given filters, newest-received
        first, plus the total count matching those filters (independent of
        limit/offset)."""
        # Every condition appended here lands in the same .where(*conditions) call
        # below, which ANDs them together -- selecting claimant_name and status both
        # narrows to their intersection, it does not union the two separately.
        conditions = []
        if policy_number is not None:
            conditions.append(Claim.policy_number == policy_number)
        if claimant_name is not None:
            conditions.append(Claim.claimant_name.ilike(f"%{claimant_name}%"))
        if claim_type is not None:
            conditions.append(Claim.claim_type == claim_type)
        if status is not None:
            conditions.append(Claim.status == status)
        if batch_id is not None:
            conditions.append(Claim.batch_id == batch_id)
        if received_after is not None:
            conditions.append(Claim.received_at >= received_after)
        if received_before is not None:
            conditions.append(Claim.received_at <= received_before)

        total = self._session.execute(
            select(func.count()).select_from(Claim).where(*conditions)
        ).scalar_one()
        stmt = (
            select(Claim)
            .where(*conditions)
            .order_by(Claim.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self._session.execute(stmt).scalars().all())
        return items, total
