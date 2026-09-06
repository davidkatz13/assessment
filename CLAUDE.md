# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI service that ingests batches of insurance claim documents. A batch is one
JSON file containing an array of claims; either every valid claim in it is persisted,
or none of it is. Backend only — no reviewer UI exists yet in this repo.

## Commands

```bash
# Setup
cp .env_template .env
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run (Option A: fully dockerized — builds the image, runs migrations, starts the API)
docker compose up --build

# Run (Option B: local dev server with hot reload, against a dockerized DB only)
docker compose up -d db
alembic upgrade head
uvicorn main:app --reload

# Tests (no DB/Docker required — see Testing strategy below)
pytest
pytest tests/services/test_batch_ingestion_service.py -k conflict   # single test

# Lint / format / typecheck (all mandated by BackendCodingStandard.doc)
black app core main.py tests alembic/env.py
mypy app core main.py --ignore-missing-imports

# New migration after changing app/models/orm.py
alembic revision --autogenerate -m "description"
alembic upgrade head

# Submit a sample batch to a running instance
./scripts/submit_batch.sh scripts/sample_batches/valid_batch.json
```

`POSTGRES_PORT` defaults to `15432` in `.env_template`, not `5432` — a local Postgres
install can silently intercept `127.0.0.1:5432` ahead of Docker's proxy on macOS, so an
uncommon port was picked deliberately. Postgres connection settings are individual
fields (`POSTGRES_HOST`/`PORT`/`USER`/`PASSWORD`/`DB`) assembled into a URL in
`core/config.py`, not one `DATABASE_URL` string — this also lets `docker-compose.yml`
reuse the exact variable names Postgres's own image expects.

## Architecture

Layered per `BackendCodingStandard.doc` (this repo's own coding standard — CSR
pattern, snake_case files/folders, <500 lines/file, type hints everywhere except
`self`/`__init__` return, PEP8 + Black + MyPy):

```
app/api/v1/        FastAPI routers. Pure HTTP glue only — read the request, call a
                    controller, shape the response. No business logic here, ever.
app/controllers/    Orchestrate service calls, decide HTTP-facing outcomes (status
                    codes), log. No direct DB/disk access.
app/services/       Business logic. Call repositories when they need the DB or disk.
app/repositories/   All SQL and all filesystem access. Owns transaction boundaries.
app/models/         orm.py (SQLAlchemy models) and schemas.py (Pydantic request/
                    response models, including `from_orm_*` mappers — ORM→schema
                    conversion lives on the schema classes, not scattered helpers).
core/               Config (pydantic-settings), DB session, logging, exceptions,
                    enums — cross-cutting, domain-agnostic.
```

A `RepositoryFactory` → `ServiceFactory` → `ControllerFactory` chain (in
`app/api/deps.py`, wired via FastAPI `Depends`) builds each layer's objects. This is
what makes services testable without a real database: tests build them directly
against hand-rolled fakes instead of going through the factories/`Depends` at all.

**Request flow for `POST /api/v1/batches`** (the one place `async def` is real —
propagated up from `UploadFile.read()`, see "async vs def" below):
`api/v1/batches.py` → `BatchController.submit_batch` →
`BatchIngestionService.ingest_from_upload` (streams the upload under a size cap) →
`.ingest()` (checksum → idempotency check → content-addressed disk write → parse →
`BatchValidationService.validate()` → duplicate-external_id check → commit-or-reject
via `BatchRepository`).

### Atomicity model (the load-bearing part of this codebase)

`BatchRepository.commit_batch` / `reject_batch` each do their DB work in one
transaction. Validation happens entirely before any DB write — errors are
accumulated across all claims (not fail-fast), and if any exist, `claims` is never
touched at all, so atomicity on the reject path is trivial. On the commit path,
claims are bulk-inserted via a Core `insert()` with a list of dicts (not
`session.add()` per row — matters once a batch has thousands of rows).

**Known gotcha, already bit once during development:** the session has
`autoflush=False` (`core/db.py`), and the bulk `insert(Claim)` in `commit_batch` is a
Core statement that bypasses the ORM unit-of-work. Without the explicit
`self._session.flush()` between `session.add(batch)` and the bulk claims insert, the
`batches` row is never sent to Postgres first, and the claims insert fails its FK
check against a `batch_id` that "doesn't exist yet." This passes MyPy and any test
against fake repositories — it only fails against a real Postgres transaction. If you
touch `commit_batch`, keep the flush.

The raw uploaded file is stored **content-addressed**
(`data/uploads/batches/<sha256>.json`) — this is deliberate and lets the disk write
happen before/outside the DB transaction safely: a write is either already at its
hash-derived path or it isn't, so it's idempotent and a rolled-back/rejected batch
just leaves a harmless orphan file, never a corrupt one.

Enum-like columns (`claims.claim_type`, `claims.status`, `batches.status`) are plain
`TEXT`, validated once at the Pydantic boundary — not a DB `CHECK` constraint or
Postgres `ENUM` type, since either would need a migration every time the business
adds a value.

### API error shapes and CORS

`POST /api/v1/batches` always returns `BatchSubmitResponse` (success or rejection —
`batch_id`/`status`/`errors[]`/etc.), on every status code including `422`/`409`.
Every other failure anywhere in the API — `413`, a bad query/path param, a malformed
body — returns `{"detail": [{"field", "message"}]}` via two handlers in `main.py`
(`BatchTooLargeError` and a `RequestValidationError` override that reshapes FastAPI's
default verbose error list). If you add a new query param that should reject bad
input with a real `422` instead of silently matching nothing, type it against
`core/enums.py` (see `claim_type`/`status` on `/claims` and `/batches`) rather than
`str` — it gets the unified error shape and OpenAPI documentation for free. CORS is
configured via `CORS_ALLOWED_ORIGINS` (comma-separated, see `core/config.py`'s
`cors_allowed_origins_list`) and applied in `main.py`.

### async vs def

Only use `async def` where something is actually awaited. `submit_batch` is async
top-to-bottom (API → controller → service) because `BatchIngestionService.
_read_within_limit` does `await file.read(...)` on the upload stream — that's a real
coroutine, and Python forces every caller up the chain to be async too. `list_batches`
and `list_claims` are plain `def` at every layer because they never await anything
(the repositories are synchronous SQLAlchemy) — FastAPI runs sync route functions in a
worker thread pool automatically, which is the honest fit here. Note the DB stack
itself is fully synchronous (sync `Session`, psycopg in sync mode); async SQLAlchemy
was judged out of scope for this project's scale.

### Testing strategy

Tests exercise `BatchValidationService` and `BatchIngestionService` directly against
hand-rolled fake repositories (`tests/services/test_batch_ingestion_service.py`) — no
real Postgres, no mocking framework. This is deliberate: the DI-via-factories
architecture exists specifically so the atomicity/idempotency rules can be tested as
plain Python, which keeps the suite fast (<0.5s) and infra-free. There is currently no
integration test against real Postgres, so a bug purely in the SQL/transaction
mechanics (like the flush gotcha above) will not be caught by `pytest` — only by
actually running the service.
