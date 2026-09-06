import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import Controllers
from app.models.schemas import PaginatedClaims

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("", response_model=PaginatedClaims)
async def list_claims(
    controllers: Controllers,
    policy_number: str | None = None,
    claimant_name: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    batch_id: uuid.UUID | None = None,
    received_after: datetime | None = None,
    received_before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedClaims:
    claim_controller = controllers.build_claim_controller()
    return claim_controller.list_claims(
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
