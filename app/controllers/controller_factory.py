from app.controllers.batch_controller import BatchController
from app.controllers.claim_controller import ClaimController
from app.repositories.repository_factory import RepositoryFactory
from app.services.service_factory import ServiceFactory


class ControllerFactory:
    """Builds controllers with their services (and, transitively, repositories)
    wired up. The API layer only ever asks this factory for a controller -- it never
    constructs a service or repository itself."""

    def __init__(
        self, repository_factory: RepositoryFactory, service_factory: ServiceFactory
    ) -> None:
        """Store the factories controllers built here are wired up through."""
        self._repository_factory = repository_factory
        self._service_factory = service_factory

    def build_batch_controller(self) -> BatchController:
        """Build a BatchController with its ingestion and query services wired up."""
        batch_repository = self._repository_factory.build_batch_repository()
        file_repository = self._repository_factory.build_file_storage_repository()
        ingestion_service = self._service_factory.build_batch_ingestion_service(
            batch_repository, file_repository
        )
        query_service = self._service_factory.build_batch_query_service(
            batch_repository
        )
        return BatchController(ingestion_service, query_service)

    def build_claim_controller(self) -> ClaimController:
        """Build a ClaimController with its query service wired up."""
        batch_repository = self._repository_factory.build_batch_repository()
        query_service = self._service_factory.build_claim_query_service(
            batch_repository
        )
        return ClaimController(query_service)
