from enum import StrEnum


class BatchStatus(StrEnum):
    """Outcome of a batch ingestion attempt."""

    COMMITTED = "committed"
    REJECTED = "rejected"


class ClaimType(StrEnum):
    """Allowed values for a claim's claim_type field."""

    AUTO = "auto"
    HEALTH = "health"
    PROPERTY = "property"
    LIFE = "life"
    OTHER = "other"


class ClaimStatus(StrEnum):
    """Allowed values for a claim's status field."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DENIED = "denied"
    PAID = "paid"
