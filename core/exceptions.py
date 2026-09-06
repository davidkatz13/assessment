class BatchProcessingError(Exception):
    """Base class for domain errors raised while ingesting a batch."""


class BatchParseError(BatchProcessingError):
    """The uploaded file was not valid JSON, or not a JSON object with a 'claims' array."""


class BatchConflictError(BatchProcessingError):
    """A DB-level conflict (e.g. a unique constraint race) was hit while committing a batch."""


class FileStorageError(BatchProcessingError):
    """Writing or reading the raw batch file on disk failed."""


class BatchTooLargeError(BatchProcessingError):
    """The upload exceeded the configured size limit before it could be fully read,
    so there's no complete file to record a rejected batch for."""
