from enum import StrEnum


class BatchStatus(StrEnum):
    COMMITTED = "committed"
    REJECTED = "rejected"


class ClaimType(StrEnum):
    AUTO = "auto"
    HEALTH = "health"
    PROPERTY = "property"
    LIFE = "life"
    OTHER = "other"


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DENIED = "denied"
    PAID = "paid"
