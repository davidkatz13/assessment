import hashlib
from pathlib import Path

from core.exceptions import FileStorageError


class FileStorageRepository:
    """Content-addressed storage for raw batch files on local disk.

    A write is a no-op if the content already exists at its hash-derived path, which is
    what makes it safe to happen before/outside the DB transaction that decides whether
    the batch is accepted: the file is never half-written, and a leftover file after a
    rejected or rolled-back batch is an inert, harmless orphan.
    """

    def __init__(self, base_dir: str) -> None:
        """Ensure the batches subdirectory under base_dir exists, ready to write to."""
        self._base_dir = Path(base_dir) / "batches"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        """Return the sha256 hex digest of content, used as its storage key."""
        return hashlib.sha256(content).hexdigest()

    def save(self, content: bytes, checksum: str) -> str:
        """Write content to its content-addressed path. Returns the storage path."""
        path = self._base_dir / f"{checksum}.json"
        if not path.exists():
            try:
                path.write_bytes(content)
            except OSError as exc:
                raise FileStorageError(
                    f"failed to write batch file for checksum {checksum}"
                ) from exc
        return str(path)
