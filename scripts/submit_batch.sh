#!/usr/bin/env bash
# Submit a batch file to the running API.
#
# Usage:
#   ./scripts/submit_batch.sh path/to/batch.json [base_url]
#
# Examples:
#   ./scripts/submit_batch.sh scripts/sample_batches/valid_batch.json
#   ./scripts/submit_batch.sh scripts/sample_batches/invalid_batch.json
#   ./scripts/submit_batch.sh scripts/sample_batches/duplicate_existing_claim.json
set -euo pipefail

FILE="${1:?usage: submit_batch.sh <path-to-batch.json> [base_url]}"
BASE_URL="${2:-http://localhost:8000}"

curl -sS -w '\nHTTP %{http_code}\n' \
  -X POST "${BASE_URL}/api/v1/batches" \
  -F "file=@${FILE};type=application/json;filename=$(basename "${FILE}")"
