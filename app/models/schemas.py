import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.orm import Batch, BatchError, Claim
from core.enums import ClaimStatus, ClaimType


class ClaimIn(BaseModel):
    """One claim record as it appears inside a submitted batch file."""

    external_id: str = Field(min_length=1)
    claimant_name: str = Field(min_length=1)
    policy_number: str = Field(min_length=1)
    claim_type: ClaimType
    amount_cents: int = Field(ge=0)
    received_at: datetime
    status: ClaimStatus = ClaimStatus.SUBMITTED
    document_text: str | None = None


class BatchErrorOut(BaseModel):
    row_index: int | None
    external_id: str | None
    field: str | None
    message: str

    @classmethod
    def from_orm_error(cls, error: BatchError) -> "BatchErrorOut":
        return cls(
            row_index=error.row_index,
            external_id=error.external_id,
            field=error.field,
            message=error.message,
        )


class BatchSubmitResponse(BaseModel):
    """Response for POST /batches, and one item's shape within GET /batches."""

    batch_id: uuid.UUID
    original_filename: str
    status: str
    claim_count: int
    submitted_at: datetime
    error_count: int = 0
    errors: list[BatchErrorOut] = Field(default_factory=list)
    truncated: bool = False

    @classmethod
    def from_orm_batch(cls, batch: Batch) -> "BatchSubmitResponse":
        errors = [BatchErrorOut.from_orm_error(error) for error in batch.errors]
        return cls(
            batch_id=batch.id,
            original_filename=batch.original_filename,
            status=batch.status,
            claim_count=batch.claim_count,
            submitted_at=batch.submitted_at,
            error_count=len(errors),
            errors=errors,
            truncated=batch.errors_truncated,
        )


class PaginatedBatches(BaseModel):
    total: int
    items: list[BatchSubmitResponse]

    @classmethod
    def from_orm_batches(cls, batches: list[Batch], total: int) -> "PaginatedBatches":
        return cls(
            total=total,
            items=[BatchSubmitResponse.from_orm_batch(batch) for batch in batches],
        )


class ClaimOut(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    external_id: str
    claimant_name: str
    policy_number: str
    claim_type: str
    amount_cents: int
    received_at: datetime
    status: str
    document_text: str | None
    created_at: datetime

    @classmethod
    def from_orm_claim(cls, claim: Claim) -> "ClaimOut":
        return cls(
            id=claim.id,
            batch_id=claim.batch_id,
            external_id=claim.external_id,
            claimant_name=claim.claimant_name,
            policy_number=claim.policy_number,
            claim_type=claim.claim_type,
            amount_cents=claim.amount_cents,
            received_at=claim.received_at,
            status=claim.status,
            document_text=claim.document_text,
            created_at=claim.created_at,
        )


class PaginatedClaims(BaseModel):
    total: int
    items: list[ClaimOut]

    @classmethod
    def from_orm_claims(cls, claims: list[Claim], total: int) -> "PaginatedClaims":
        return cls(
            total=total, items=[ClaimOut.from_orm_claim(claim) for claim in claims]
        )
