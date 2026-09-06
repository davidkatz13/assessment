from datetime import datetime

from fastapi import UploadFile

from app.models.schemas import BatchSubmitResponse, PaginatedBatches
from app.services.batch_ingestion_service import (
    BatchIngestionResult,
    BatchIngestionService,
)
from app.services.batch_query_service import BatchQueryService
from core.enums import BatchStatus
from core.logging import get_logger

logger = get_logger(__name__)


class BatchController:
    """Orchestrates the batch endpoints: calls into services, decides the HTTP-facing
    outcome of a submission, logs it, and constructs the response schema. No business
    logic of its own (that lives in the services) and no direct DB/disk access (that
    lives in the repositories) -- this class only ever talks to services."""

    def __init__(
        self, ingestion_service: BatchIngestionService, query_service: BatchQueryService
    ) -> None:
        self._ingestion_service = ingestion_service
        self._query_service = query_service

    async def submit_batch(self, file: UploadFile) -> tuple[BatchSubmitResponse, int]:
        result = await self._ingestion_service.ingest_from_upload(file)
        self._log_outcome(result)
        return BatchSubmitResponse.from_orm_batch(
            result.batch
        ), self._resolve_status_code(result)

    def list_batches(
        self,
        *,
        status: str | None,
        submitted_after: datetime | None,
        submitted_before: datetime | None,
        limit: int,
        offset: int,
    ) -> PaginatedBatches:
        items, total = self._query_service.list_batches(
            status=status,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            limit=limit,
            offset=offset,
        )
        return PaginatedBatches.from_orm_batches(items, total)

    @staticmethod
    def _resolve_status_code(result: BatchIngestionResult) -> int:
        if result.conflicted:
            return 409
        return 201 if result.batch.status == BatchStatus.COMMITTED else 422

    @staticmethod
    def _log_outcome(result: BatchIngestionResult) -> None:
        batch = result.batch
        if result.conflicted:
            logger.error("batch %s conflicted while committing", batch.id)
        elif batch.status == BatchStatus.COMMITTED:
            logger.info(
                "batch %s committed with %d claim(s)", batch.id, batch.claim_count
            )
        else:
            logger.warning(
                "batch %s rejected with %d error(s)", batch.id, len(batch.errors)
            )
