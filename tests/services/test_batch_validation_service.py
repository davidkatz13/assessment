import json

import pytest

from app.services.batch_validation_service import BatchValidationService
from core.exceptions import BatchParseError


def _service(max_claims_per_batch: int = 5000) -> BatchValidationService:
    return BatchValidationService(max_claims_per_batch=max_claims_per_batch)


def _claim(**overrides) -> dict:
    base = {
        "external_id": "CLM-1",
        "claimant_name": "Jane Doe",
        "policy_number": "POL-1",
        "claim_type": "auto",
        "amount_cents": 1000,
        "received_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestParseClaims:
    def test_valid_json_returns_claims_array(self):
        content = json.dumps({"claims": [_claim()]}).encode()

        claims = _service().parse_claims(content)

        assert claims == [_claim()]

    def test_invalid_json_raises_batch_parse_error(self):
        with pytest.raises(BatchParseError):
            _service().parse_claims(b"not json at all {")

    def test_missing_claims_key_raises_batch_parse_error(self):
        with pytest.raises(BatchParseError):
            _service().parse_claims(json.dumps({"not_claims": []}).encode())

    def test_claims_not_a_list_raises_batch_parse_error(self):
        with pytest.raises(BatchParseError):
            _service().parse_claims(json.dumps({"claims": "not a list"}).encode())


class TestValidate:
    def test_all_valid_claims_produce_no_errors(self):
        result = _service().validate(
            [_claim(external_id="CLM-1"), _claim(external_id="CLM-2")]
        )

        assert result.errors == []
        assert [c["external_id"] for c in result.valid_claims] == ["CLM-1", "CLM-2"]

    def test_missing_required_field_is_reported_with_row_index(self):
        result = _service().validate([_claim(), _claim(claimant_name="")])

        assert len(result.errors) == 1
        assert result.errors[0]["row_index"] == 1
        assert result.errors[0]["field"] == "claimant_name"

    def test_invalid_claim_type_is_rejected(self):
        result = _service().validate([_claim(claim_type="not_a_real_type")])

        assert len(result.errors) == 1
        assert result.errors[0]["field"] == "claim_type"

    def test_negative_amount_cents_is_rejected(self):
        result = _service().validate([_claim(amount_cents=-1)])

        assert len(result.errors) == 1
        assert result.errors[0]["field"] == "amount_cents"

    def test_duplicate_external_id_within_batch_is_rejected(self):
        result = _service().validate(
            [_claim(external_id="CLM-1"), _claim(external_id="CLM-1")]
        )

        assert len(result.errors) == 1
        assert result.errors[0]["row_index"] == 1
        assert "duplicate" in result.errors[0]["message"]

    def test_batch_exceeding_max_claims_is_rejected_as_a_single_error(self):
        claims = [_claim(external_id=f"CLM-{i}") for i in range(3)]

        result = _service(max_claims_per_batch=2).validate(claims)

        assert len(result.errors) == 1
        assert result.errors[0]["row_index"] is None
        assert result.valid_claims == []

    def test_status_defaults_to_submitted_when_omitted(self):
        result = _service().validate([_claim()])

        assert result.valid_claims[0]["status"] == "submitted"

    def test_accumulates_errors_across_multiple_bad_rows_instead_of_failing_fast(self):
        result = _service().validate(
            [
                _claim(claim_type="bogus"),
                _claim(external_id="CLM-2", amount_cents=-5),
                _claim(external_id="CLM-3"),
            ]
        )

        assert len(result.errors) == 2
        assert len(result.valid_claims) == 1
