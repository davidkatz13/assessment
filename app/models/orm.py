import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Shared declarative base. All models must inherit from this one instance of it
    (not DeclarativeBase directly) so they share a single MetaData/registry -- that's
    what relationship() resolution and Alembic's autogenerate both rely on."""


class Batch(Base):
    """One submitted batch upload: metadata about the raw file plus the outcome."""

    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int]
    checksum_sha256: Mapped[str] = mapped_column(Text, index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, index=True)
    claim_count: Mapped[int] = mapped_column(default=0)
    errors_truncated: Mapped[bool] = mapped_column(default=False)
    submitted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), index=True
    )

    errors: Mapped[list["BatchError"]] = relationship(back_populates="batch")
    claims: Mapped[list["Claim"]] = relationship(back_populates="batch")


class BatchError(Base):
    """One validation or conflict error recorded against a rejected batch."""

    __tablename__ = "batch_errors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True
    )
    row_index: Mapped[int | None]
    external_id: Mapped[str | None] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)

    batch: Mapped["Batch"] = relationship(back_populates="errors")


class Claim(Base):
    """A single persisted claim, always belonging to exactly one committed batch."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(Text, unique=True, index=True)
    claimant_name: Mapped[str] = mapped_column(Text)
    policy_number: Mapped[str] = mapped_column(Text, index=True)
    claim_type: Mapped[str] = mapped_column(Text, index=True)
    amount_cents: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(Text, index=True)
    document_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    batch: Mapped["Batch"] = relationship(back_populates="claims")
