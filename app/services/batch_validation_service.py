import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.models.schemas import ClaimIn
from core.exceptions import BatchParseError


@dataclass
class ClaimValidationResult:
    """Only meaningful together: valid_claims is only safe to persist when errors is
    empty -- the batch is all-or-nothing, so a caller must not cherry-pick from
    valid_claims while errors is non-empty."""

    valid_claims: list[dict[str, Any]] = field(default_factory=list)
    external_id_to_row_index: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)


class BatchValidationService:
    """Pure validation logic for a batch payload: parsing, per-claim schema and
    business-rule checks, and duplicate detection within the batch itself.

    Never touches the DB or disk. Detecting a duplicate external_id against *existing*
    claims requires a repository call, so that check is layered on top by the caller
    (the controller) using external_id_to_row_index to attribute the resulting error
    back to the right row -- this service only knows about the batch in isolation.
    """

    def __init__(self, max_claims_per_batch: int) -> None:
        """Store the configured cap on how many claims a single batch may contain."""
        self._max_claims_per_batch = max_claims_per_batch

    def parse_claims(self, content: bytes) -> list[Any]:
        """Parse the raw batch file into its list of (still-unvalidated) claims.

        Raises BatchParseError if content isn't valid JSON, or isn't a JSON object
        with a 'claims' array.
        """
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BatchParseError(f"file content is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
            raise BatchParseError("expected a JSON object with a 'claims' array")
        return payload["claims"]

    def validate(self, raw_claims: list[Any]) -> ClaimValidationResult:
        """Validate every raw claim -- schema, business rules, and duplicate
        external_id within the batch -- accumulating all errors rather than
        stopping at the first one found."""
        if len(raw_claims) > self._max_claims_per_batch:
            return ClaimValidationResult(
                errors=[
                    {
                        "row_index": None,
                        "external_id": None,
                        "field": "claims",
                        "message": (
                            f"batch has {len(raw_claims)} claims, exceeds the maximum "
                            f"of {self._max_claims_per_batch}"
                        ),
                    }
                ]
            )

        result = ClaimValidationResult()
        seen_external_ids: set[str] = set()

        for index, raw_claim in enumerate(raw_claims):
            external_id = (
                raw_claim.get("external_id") if isinstance(raw_claim, dict) else None
            )
            try:
                claim = ClaimIn.model_validate(raw_claim)
            except ValidationError as exc:
                result.errors.extend(self._to_row_errors(index, external_id, exc))
                continue

            if claim.external_id in seen_external_ids:
                result.errors.append(
                    {
                        "row_index": index,
                        "external_id": claim.external_id,
                        "field": "external_id",
                        "message": "duplicate external_id within this batch",
                    }
                )
                continue

            seen_external_ids.add(claim.external_id)
            result.external_id_to_row_index[claim.external_id] = index
            result.valid_claims.append(claim.model_dump())

        return result

    @staticmethod
    def _to_row_errors(
        index: int, external_id: str | None, exc: ValidationError
    ) -> list[dict[str, Any]]:
        """Flatten one Pydantic ValidationError into our row-error dict shape."""
        return [
            {
                "row_index": index,
                "external_id": external_id,
                "field": ".".join(str(part) for part in error["loc"]) or None,
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
