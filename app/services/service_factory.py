from app.repositories.batch_repository import BatchRepository
from app.repositories.file_storage_repository import FileStorageRepository
from app.services.batch_ingestion_service import BatchIngestionService
from app.services.batch_query_service import BatchQueryService
from app.services.batch_validation_service import BatchValidationService
from app.services.claim_query_service import ClaimQueryService
from core.config import settings


class ServiceFactory:
    """Builds services with their configuration and repository dependencies wired
    up, so callers (controllers) never construct a service -- or read settings.py --
    themselves."""

    def build_batch_validation_service(self) -> BatchValidationService:
        return BatchValidationService(
            max_claims_per_batch=settings.max_claims_per_batch
        )

    def build_batch_ingestion_service(
        self, batch_repository: BatchRepository, file_repository: FileStorageRepository
    ) -> BatchIngestionService:
        return BatchIngestionService(
            self.build_batch_validation_service(),
            batch_repository,
            file_repository,
            max_upload_size_bytes=settings.max_batch_file_size_bytes,
            max_reported_errors=settings.max_reported_errors,
        )

    def build_batch_query_service(
        self, batch_repository: BatchRepository
    ) -> BatchQueryService:
        return BatchQueryService(batch_repository)

    def build_claim_query_service(
        self, batch_repository: BatchRepository
    ) -> ClaimQueryService:
        return ClaimQueryService(batch_repository)
