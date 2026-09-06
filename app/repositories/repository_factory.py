from sqlalchemy.orm import Session

from app.repositories.batch_repository import BatchRepository
from app.repositories.file_storage_repository import FileStorageRepository
from core.config import settings


class RepositoryFactory:
    """Builds repositories with their dependencies wired up.

    BatchIngestionService needs two repositories (DB + disk); constructing them by
    hand at every call site would duplicate that wiring everywhere it's needed. This
    factory is the single place that knows how to build a repository, which is also
    what lets tests substitute a fake FileStorageRepository/BatchRepository without
    touching the service under test.
    """

    def __init__(self, session: Session) -> None:
        """Store the request-scoped session repositories built here will share."""
        self._session = session

    def build_batch_repository(self) -> BatchRepository:
        """Build a BatchRepository bound to this factory's session."""
        return BatchRepository(self._session)

    def build_file_storage_repository(self) -> FileStorageRepository:
        """Build a FileStorageRepository rooted at the configured upload directory."""
        return FileStorageRepository(settings.upload_dir)
