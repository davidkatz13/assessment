import uuid
from datetime import datetime

from app.models.schemas import PaginatedClaims
from app.services.claim_query_service import ClaimQueryService


class ClaimController:
    """Orchestrates the claims search endpoint. Thin today (one service, no
    branching), kept as its own controller for symmetry with BatchController and
    because claims search is a distinct use case from batch ingestion."""

    def __init__(self, query_service: ClaimQueryService) -> None:
        self._query_service = query_service

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
    ) -> PaginatedClaims:
        items, total = self._query_service.list_claims(
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
        return PaginatedClaims.from_orm_claims(items, total)
