import uuid
from datetime import datetime

from app.models.orm import Claim
from app.repositories.batch_repository import BatchRepository


class ClaimQueryService:
    """Search/filtering for claims. Thin on top of the repository today, same
    rationale as BatchQueryService."""

    def __init__(self, batch_repository: BatchRepository) -> None:
        """Store the repository this service delegates all queries to."""
        self._batch_repository = batch_repository

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
        """Return a page of claims matching the given filters, plus the total count."""
        return self._batch_repository.list_claims(
            policy_number=policy_number,
            claimant_name=claimant_name,
            claim_type=claim_type,
            status=status,
            batch_id=batch_id,
            received_after=received_after,
            received_before=received_before,
            limit=limit,
            offset=offset,
        )
