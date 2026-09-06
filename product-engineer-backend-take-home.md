# Product Engineer (Backend-leaning) Take-Home: Batch Document Processor

Timebox: around 4 hours.

Build a small FastAPI service that ingests insurance claim documents in batches. The core of the assignment is backend ownership: API contract, validation, SQL schema, transaction handling, tests, and trade-offs. You also build a small reviewer UI on top of the API, so we can see how you treat a surface that isn't your main focus.

## How to approach this

Treat this as code a team will inherit and keep building on. We care about the foundation you set, not a finished product and not a framework. Aim for choices another engineer could pick up next week and extend without fighting you: clear boundaries, honest naming, types at the seams, and a test or two that show the pattern you'd want repeated.

Right-sizing is the whole game. Under-build and it falls apart on contact; over-build (premature abstractions, a config system for one environment, layers you don't need yet) and you've buried the foundation under scaffolding. We read for where you chose to invest and where you deliberately chose to stop.

This bar applies to the **entire** submission, including the reviewer UI. The UI is smaller in scope, not lower in quality: a bare-but-clean surface beats a polished-but-rotten one. Don't let your standard drop just because a part "isn't the point."

Use your real toolchain, AI assistants included. We don't care how the code was produced; we care that you own every line. You walk us through the submission and defend your decisions in the next round, so build something you fully understand.

## Scenario

MarvelX receives batches of insurance claim documents from customers. A reviewer needs to submit a batch, know whether it landed successfully, and inspect previous batches. The important invariant: a batch is atomic. Either every valid claim in the batch is persisted, or none of it is.

## Required Scope

Backend:

- FastAPI service with 2-3 REST endpoints.
- SQL persistence. SQLite is fine; Postgres is fine if setup stays simple.
- Batch ingestion endpoint with transactional all-or-nothing behavior.
- Basic validation and explicit error responses.
- At least one search or filtering capability.
- Tests for the main path and at least one failure/rollback path.
- A documented way for us to submit batches ourselves (a script, a seed file, a curl snippet, whatever is simplest) without editing your code. We will send batches you did not write, including ones we expect to fail.

Reviewer UI:

- Minimal UI to paste or upload a batch payload and submit it to the API.
- Shows success, validation failure, and server/API failure states.
- Shows previously submitted batches or lets the reviewer inspect one submitted batch.
- Small in scope, and you can skip the visual polish. Keep the bar high on the parts that outlast a demo: a clean data layer, real handling of the loading/error/empty states, and types at the API boundary. This is where we see whether the API is actually usable from the other side.

Documentation:

- README with setup/run/test commands.
- Explain schema choices, transaction handling, validation choices, and what you skipped because of the timebox.
- One short section: what you'd build next, and what you deliberately left out and why. This is where we read your right-sizing judgment.
- Roughly how long you actually spent, and what you cut to fit.
- One or two sentences: the next feature here gets built by someone less experienced than you, working with an AI agent. What in your code are they most likely to get wrong, and why?

## Suggested Data Shape

You may choose your own shape. If useful, model a claim with fields such as:

- external_id
- claimant_name
- policy_number
- claim_type
- amount_cents
- received_at
- status
- document_text

Add or remove fields if your design needs it. The exact schema matters less than whether the choices are coherent and documented.

## Submission

Send a repository link or archive with the code and README. Include enough setup instructions that we can run the service, the UI, and the tests locally.

## What We Evaluate

- API and schema design.
- Transactional correctness, against batches we send, including failures you did not anticipate.
- Query/search/filtering design.
- Error handling and edge cases.
- Test quality.
- A consistent foundation-grade bar across the whole submission, the reviewer UI included: clean enough that a teammate could extend it, without over-building it.
- Right-sizing judgment: investing in what's load-bearing, deferring the rest on purpose, and saying which is which.
- README clarity and honest trade-offs.
