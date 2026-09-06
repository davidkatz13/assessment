import uuid
from datetime import datetime

from app.models.orm import Batch
from app.repositories.batch_repository import BatchRepository


class BatchQueryService:
    """Search/listing for batches. Thin on top of the repository today, but this is
    the seam where business rules about *which* batches a caller may see would go if
    that's ever needed (e.g. tenant scoping) -- the controller should never reach
    past this into the repository directly."""

    def __init__(self, batch_repository: BatchRepository) -> None:
        """Store the repository this service delegates all queries to."""
        self._batch_repository = batch_repository

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
        """Return a page of batches matching the given filters, plus the total count."""
        return self._batch_repository.list_batches(
            batch_id=batch_id,
            status=status,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            limit=limit,
            offset=offset,
        )
