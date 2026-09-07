# Batch Document Processor — Backend

A FastAPI service that ingests batches of insurance claim documents. A batch is one
JSON file containing an array of claims; either every valid claim in it is persisted,
or none of it is. This submission covers the **backend** only — see [What's next /
deliberately left out](#whats-next--deliberately-left-out).

## Intended functionality

- `POST /api/v1/batches` — upload one JSON batch file. Every submission that reaches
  the service (i.e. isn't rejected outright by a missing file or exceeding the size
  cap) is recorded as a batch — `committed` or `rejected` — so there's always an
  auditable record of what was sent, including batches we expect to fail.
- `GET /api/v1/batches` — batch history, filterable by `status` and a submitted-at
  date range. Each item includes its errors when rejected, so a batch is fully
  inspectable from the list alone.
- `GET /api/v1/claims` — search/filter persisted claims by `policy_number`,
  `claimant_name` (substring), `claim_type`, `status`, `batch_id`, and a
  `received_at` date range.

## Setup

Two ways to run it. Either way, start from:

```bash
cp .env_template .env
```

### Option A — fully dockerized

```bash
docker compose up --build
```

This starts Postgres, runs `alembic upgrade head`, and starts the API on
`http://localhost:8000`.

### Option B — local dev server against a dockerized DB (hot reload)

```bash
docker compose up -d db
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload
```

Either way, the API is at `http://localhost:8000` (interactive docs at `/docs`).

### Environment variables

See `.env_template`. Postgres connection details are individual fields
(`POSTGRES_HOST`/`PORT`/`USER`/`PASSWORD`/`DB`), assembled into a SQLAlchemy URL in
`core/config.py`, rather than one `DATABASE_URL` string — this also lets
`docker-compose.yml` reuse the exact same variable names Postgres's own Docker image
expects. Note `POSTGRES_PORT` defaults to `15432` in `.env_template`, not `5432` — an
uncommon port was picked deliberately, since a locally-running Postgres install can
silently intercept `127.0.0.1:5432` ahead of Docker's own proxy on macOS.

`CORS_ALLOWED_ORIGINS` is a comma-separated list of origins allowed to call this API
from a browser (default `http://localhost:3000`, for a local Next.js dev server) —
see `core/config.py`'s `cors_allowed_origins_list` and `main.py`'s `CORSMiddleware`
registration.

### Submitting batches yourself

```bash
./scripts/submit_batch.sh scripts/sample_batches/valid_batch.json
./scripts/submit_batch.sh scripts/sample_batches/invalid_batch.json
./scripts/submit_batch.sh scripts/sample_batches/duplicate_existing_claim.json   # after valid_batch.json has been submitted once
```

Or with plain curl:

```bash
curl -X POST http://localhost:8000/api/v1/batches \
  -F "file=@scripts/sample_batches/valid_batch.json;type=application/json"
```

`scripts/sample_batches/` also documents the expected payload shape.

### Tests

```bash
pytest
```

No database or Docker required — see [Testing strategy](#testing-strategy) for why.

## Architecture

Layered per the coding standard this repo follows: **Controller → Service →
Repository**, plus a Factory per layer for dependency wiring.

```
app/
  api/v1/            FastAPI routers. Pure HTTP glue: read the request, call a
                      controller, shape the response. No business logic.
  controllers/        Orchestrate calls to services, decide HTTP-facing outcomes
                      (status codes), log. No direct DB/disk access.
  services/           Business logic. Ingestion, validation, and query services call
                      repositories when they need the DB or disk.
  repositories/        All SQL and all filesystem access. Owns transaction boundaries.
  models/              SQLAlchemy models (orm.py) and Pydantic request/response
                      schemas (schemas.py), including the ORM -> schema mappers.
core/                Config (pydantic-settings), DB session, logging, exceptions,
                      enums — cross-cutting, domain-agnostic.
```

A `RepositoryFactory` and `ServiceFactory` (and a `ControllerFactory` above them)
build each layer's objects with their dependencies wired up, rather than every call
site constructing its own repositories/services by hand. This is also what makes
`BatchIngestionService` testable in isolation: unit tests build it against hand-rolled
fake repositories instead of a real database (see `tests/services/`).

## Design choices

### Schema

- **`batches`** — one row per upload attempt (committed or rejected), with the raw
  file's checksum/storage path and outcome counts.
- **`batch_errors`** — a real table with a `batch_id` FK, not a JSON blob on
  `batches`. Query-friendly, and doesn't force a schema migration just to change what
  an error looks like.
- **`claims`** — one row per persisted claim, `external_id` globally unique. Enum-like
  columns (`claim_type`, `status`) are plain `TEXT`, validated once at the Pydantic
  boundary rather than with a DB `CHECK` constraint or Postgres `ENUM` type — either
  of those would need a migration every time the business adds a claim type, which
  defeats the point of calling it "app-level."

### File storage

The raw uploaded file is written to **content-addressed** storage
(`data/uploads/batches/<sha256>.json`), with the DB storing the path — the same
pattern a production version would use with an S3 key instead of a local path. This
resolves the "dual write" problem that having a DB transaction *and* a disk write can
never fully share: a write is either already at its hash-derived path or it isn't, and
writing it twice is a no-op, so the file can safely be written *before and outside*
the DB transaction. If the transaction later rejects or rolls back, the file becomes
an orphan, but an inert, harmless one — nothing references it, and it's safe to sweep
later (not built).

### Transaction handling / atomicity

The whole flow, in order:

1. Read the upload under a size cap (streamed, so an oversized file fails before being
   fully buffered).
2. Hash it. If a batch with this exact checksum was already processed, return that
   result instead of reprocessing — makes retries from an upstream system idempotent
   without a separate idempotency-key mechanism.
3. Write the file to content-addressed storage (see above).
4. Parse the JSON, then validate every claim — schema, business rules, and duplicate
   `external_id` detection (within the batch, and against existing rows via one `IN
   (...)` query) — accumulating **all** errors rather than stopping at the first one,
   so a reviewer sees everything wrong in a single response.
5. **Any errors → reject.** One transaction inserts the `batches` row
   (`status=rejected`) and its `batch_errors` rows. `claims` is never touched on this
   path, so atomicity is trivial.
6. **No errors → commit.** One transaction inserts the `batches` row
   (`status=committed`) and bulk-inserts every claim. Claims are written via a single
   Core `insert()` with a list of dicts rather than one `session.add(Claim(...))` per
   row — SQLAlchemy 2.0's `insertmanyvalues` turns that into a small number of
   multi-row `INSERT` statements instead of paying per-instance ORM overhead for every
   claim, which matters once a batch has thousands of rows. A `MAX_CLAIMS_PER_BATCH`
   cap (default 5,000) bounds worst-case request latency regardless.
7. If an *unanticipated* DB error surfaces during that commit — e.g. a race where two
   concurrent requests both pass step 4's duplicate check for the same `external_id`
   and one's insert violates the unique constraint after the other commits — the
   transaction is rolled back in full, and a fresh transaction records a `rejected`
   batch describing the conflict. The API returns `409`.

### Validation

Two layers, both real: transport-level (is there a file, does it end in `.json`,
is it under the size cap) and content-level (JSON structure, per-claim schema via
Pydantic, business rules like `amount_cents >= 0`, duplicate detection). Declared
multipart `content-type` is recorded but not enforced — real-world clients are
inconsistent about what they set there for a `.json` file, and the actual JSON parse
step already covers correctness; gating on it would reject legitimate uploads for a
cosmetic reason.

### API error shapes

Two contracts, not one, and a frontend needs to branch on which endpoint it called
rather than assume a single error envelope everywhere:

- `POST /api/v1/batches` always returns `BatchSubmitResponse` — `{batch_id, status,
  claim_count, submitted_at, error_count, errors, truncated}` — on **every** outcome
  (`201` committed, `422` content rejected, `409` conflict). This is a resource
  representation, not a generic error, which is why it doesn't match the shape below.
- Every other failure across the whole API — a `413` oversized upload, a malformed
  query/path param (bad UUID, bad date, an invalid `claim_type`/`status` value),
  a malformed request body elsewhere — returns the same
  `{"detail": [{"field": "<name>", "message": "<why>"}]}` envelope. This is a single
  `RequestValidationError` handler in `main.py` reshaping FastAPI's default (verbose,
  `loc`/`msg`/`type`/`input`/`url` per error) into something consistent, plus the
  `BatchTooLargeError` handler emitting the same shape for `413`.

`claim_type` and `status` on `GET /api/v1/claims`, and `status` on `GET
/api/v1/batches`, are typed against `core/enums.py` (not `str`) specifically so a
typo (`?status=aproved`) is a `422` in this shape, not a silent `200` with an empty
result set indistinguishable from "no matches." FastAPI documents the allowed values
for these in `/openapi.json` automatically as a result, too.

## Known limitations (frontend-facing)

Surfaced while a separate session started building the reviewer UI against this API:

- **Size/claim-count limits aren't exposed by any endpoint.** `MAX_BATCH_FILE_SIZE_BYTES`
  (25 MiB) and `MAX_CLAIMS_PER_BATCH` (5,000) live only in this service's config. A
  frontend wanting a fast pre-upload check has to hardcode matching constants —
  which can silently drift if `.env` changes later. Deliberately not fixed with a
  config endpoint for this pass; keep the two in sync by hand if either changes.
- **A `413` (oversized upload) never gets a `batches` row.** By design: the upload is
  never fully buffered or hashed once it exceeds the cap, so there's no complete
  artifact to record. This means batch history can never show an "attempted, too
  large" entry — a frontend should treat `413` as an ephemeral, toast-only error, not
  something that will appear on a later list refresh.
- **`external_id` is globally unique with no update path.** Once a claim is
  committed, that `external_id` can never appear in any future batch again — a
  duplicate is always an error, never a valid resubmission or correction. This is the
  intended model (claims are append-only, closer to an audit log than a mutable
  record), not a gap.
- **No auth, no rate limiting, no `/health` endpoint.** Reasonable omissions given
  this project's scope — deliberate, not oversights.

## Testing strategy

Tests exercise the business logic (`BatchValidationService`, `BatchIngestionService`)
directly, against hand-rolled fake repositories — not a real Postgres, and not
mocks from a mocking framework. This was a deliberate choice: the DI-via-factories
architecture exists specifically so the atomicity/idempotency rules can be tested as
plain Python without needing a database at all, which makes the suite fast (<0.5s) and
runnable with zero infrastructure. Coverage includes the main path, the rollback path
(an invalid claim rejects the whole batch, nothing partial is ever handed to a
repository), the duplicate-`external_id` path, the unanticipated-DB-conflict path, and
the idempotent-replay path.

What this doesn't cover: the actual SQL (index usage, the real `IntegrityError` a
unique-constraint race raises, the FK ordering between a `batches` insert and a bulk
`claims` insert). That gap is real — see the next section.

## What's next / deliberately left out

- **Binary document attachments** (PDF/image bytes per claim). The brief's own
  suggested schema uses a text field; building real attachment handling would be
  scope invented for its own sake, not scope the brief asked for.
- **Pull-based ingestion from 3rd-party systems** (Confluence, email, CRM). A
  different engineering problem — per-source auth, polling/webhooks, format
  normalization — that would dominate the time budget without adding signal about
  batch/transaction/validation correctness. The service layer never touches
  HTTP/multipart directly, so a future pull-connector would hand
  `BatchIngestionService` a manifest + bytes fetched from wherever, no rearchitecture
  needed.
- **CSV/other batch formats.** JSON only.
- **A repository-level integration test against real Postgres.** The unit tests below
  the DB line give confidence in the business logic; they cannot, by construction,
  catch a bug in the actual SQL. One did slip through this way during development
  (see below) — a small integration suite against a real (disposable, separate-from-
  dev) test database is the natural next investment, deliberately not built now.
- **Orphaned file cleanup, multi-document-per-claim, serving document bytes back
  out.** None of these are required by anything currently built.
- **Blob storage instead of local disk.** `data/uploads/batches/<sha256>.json` is a
  stand-in for an object store. The content-addressed key is exactly what a
  production version would use as an S3 key — swapping the storage backend doesn't
  change the write-before-transaction pattern above, just where the bytes land.
- **A genuinely async DB stack (async SQLAlchemy + `asyncpg`).** The DB session is
  fully synchronous (see "async vs def" in `CLAUDE.md`), and `submit_batch` is
  `async def` because `UploadFile.read()` is truly awaited. That means the
  synchronous `commit_batch`/`reject_batch` calls run *inside* that coroutine on the
  event-loop thread — for a large batch's insert, that blocks the loop for the
  duration of the DB call, stalling every other concurrent request on any endpoint,
  not just batch uploads. Fine at this project's scale; a real async driver
  end-to-end is the fix if throughput ever mattered. Separately, the streaming read
  in `BatchIngestionService._read_within_limit` checks the size cap after every 1 MiB
  chunk and aborts as soon as it's crossed, so an oversized upload (e.g. 10GB) never
  buffers past roughly one cap's worth in memory — but there's no per-read timeout,
  so a client trickling bytes slowly while staying under the cap can still hold a
  connection open with no mitigation today.
- **A `pg_trgm` index on `claims.claimant_name`.** The search there is
  `ILIKE '%term%'` (`app/repositories/batch_repository.py`) — a leading wildcard, so
  no plain B-tree index helps; it's a full scan. Fine at this scale; a trigram index
  is the real fix if this ever mattered in production.

## Time spent

4-5 hours of development time

## Where the next person (paired with an AI agent) is most likely to get it wrong

`BatchRepository.commit_batch` mixes an ORM `session.add(batch)` with a Core-style
bulk `session.execute(insert(Claim), rows)` in the same transaction, and the session
has `autoflush=False`. That combination means the `batches` row is **not** actually
sent to Postgres until something forces a flush — so the explicit `self._session.flush()`
between the two is load-bearing, not decorative. Skip it (easy to do if you're adding
a new bulk-inserted table and pattern-match on the `insert(Claim)` call without
noticing the flush above it) and every claim insert fails its foreign key check
against a `batch_id` that "doesn't exist yet," even though the code type-checks fine
and passes any test written against fake repositories. This is exactly the bug that
shipped in the first draft of this file during development — it only surfaced once
the code ran against real Postgres, not in review or in the unit tests, which is the
scenario an AI-assisted change is likely to repeat: plausible-looking code that
compiles and passes fakes, wrong the moment it touches a real transaction.
