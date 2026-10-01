# Part 13 implementation and verification

Verified October 1, 2026 (Asia/Karachi).

Part 13 builds on the Part 12 assistant schema at Alembic revision `20261001_0011`. No schema change was required: privacy-conscious request metrics and response feedback use the existing user-scoped `audit_events` table. No migration was created, edited, or squashed. The development PostgreSQL volume was preserved.

## Reliability architecture

Every response passes through a strict `AssistantAnswer` schema with bounded answer, citation, evidence-reference, freshness, and limitation fields. The validator requires citations to match the ordered, user-authorized retrieval set exactly, including record ID, source type, excerpt, record path, date, and freshness. It also requires numbered citation markers, source-derived freshness labels, the configured output bound, and exact copies of deterministic calculation references.

Malformed provider output, fabricated citations, altered calculations, missing markers, provider errors, and oversized output fall back to the deterministic evidence response. The external provider never receives a financial write tool. Gains, FIFO basis, fees, tax estimates, property yields, and marketplace margins continue to come from existing stored deterministic analyses rather than generated arithmetic.

The assistant explicitly refuses requests to place or modify trades, marketplace purchases or listings, and property offers. Imported passages and listing text remain untrusted evidence. Conflicting stored property or marketplace values are labeled as conflicts rather than silently resolved. Missing evidence produces an abstention and asks what source data the user wants to add.

## Evaluation suite

`backend/evaluation/cases.v1.json` is the versioned `part13-v1` dataset. It defines 14 synthetic cases covering supported citations, missing and stale evidence, conflicting sources, cross-user access, injected instructions in passages and listing text, tax/gain calculations, property yield comparisons, marketplace margin comparisons, prohibited actions, and unsupported claims.

`python -m evaluation.runner` creates isolated synthetic users and authorized evidence, disables the provider, replaces network access with a failing stub, exercises the HTTP API, and writes JSON plus Markdown. Pass/fail checks are deterministic; no LLM judge is used. Calculation cases compare exact saved service outputs, with Decimal equality for monetary values. Prohibited-action cases compare financial-domain row counts immediately before and after the request.

Checked-in results:

- [Machine-readable JSON](evaluations/part-13-evaluation.json)
- [Concise Markdown](evaluations/part-13-evaluation.md)

Result: **14/14 cases passed**. Metric checks: citation coverage 13/13, citation ownership 13/13, abstention 2/2, stale labels 1/1, conflict labels 1/1, deterministic calculation agreement 3/3, read-only refusals 3/3, read-only state boundaries 3/3, cross-user blocking 1/1, and prompt-injection handling 2/2.

## Audit events and privacy

Each assistant request records only request outcome, configured provider mode, returned mode, elapsed milliseconds, citation count, validation state, and fallback state. It does not record the prompt, answer, retrieved passages, provider token, secret, or financial values. Aggregate metrics are calculated only from the authenticated user's events.

Response feedback stores only the owned assistant message ID, a bounded quality category, and flags documenting that it contains no prompt/answer and creates no financial action. Another user cannot report or inspect the message. Conversation deletion removes messages and their content; minimal audit events remain as operational history until the account/database retention process removes them.

Tests submit a unique sensitive marker and assert it is absent from both captured logs and serialized audit details.

## Mobile behavior

The Expo assistant links each answer to an “Assistant limitations and evidence” screen. The view shows deterministic or LLM mode, source dates, freshness/estimate labels, citations, calculation references, and limitations. A user can submit a categorized incorrect/unsupported-response report. The screen states that this report does not create or change a financial action. It uses the existing secure token and Expo Router patterns and adds no native dependency.

## Main changed files

- `backend/evaluation/cases.v1.json`, `backend/evaluation/runner.py`, and generated reports under `docs/evaluations/`
- `backend/app/assistant_service.py`, `routes_assistant.py`, and `schemas_assistant.py`
- `backend/tests/test_assistant_reliability.py`
- `backend/Dockerfile`, `.env.example`, and `compose.yaml`
- `mobile/src/app/assistant.tsx`, `assistant-evidence.tsx`, and `_layout.tsx`
- `README.md` and this report

## Commands and results

```powershell
docker compose --profile test rm -sf test-db
docker compose --profile test run --build --rm test
docker compose --profile test run --rm -v "${PWD}\docs\evaluations:/reports" test python -m evaluation.runner --json /reports/part-13-evaluation.json --markdown /reports/part-13-evaluation.md
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo install --check
npx.cmd expo-doctor
Set-Location ..
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec api alembic current
docker compose exec api alembic check
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
docker compose exec db psql -U wealth_local -d wealth_manager -tAc "SELECT system_identifier FROM pg_control_system();"
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
git diff --check
```

Results recorded during this run:

- Offline deterministic evaluation: **14/14 passed**, provider disabled, network unavailable.
- Clean disposable-database migration from base through `20261001_0011`: passed.
- Complete backend suite: **87 passed**, with one upstream Starlette TestClient deprecation warning.
- Mobile TypeScript: passed.
- Expo lint: passed.
- `expo install --check`: dependencies up to date.
- Expo Doctor: **21/21 checks passed**.
- Development Alembic state: `20261001_0011 (head)`; `alembic check` found no pending model operations.
- Docker Compose configuration: valid.
- Development API and PostgreSQL containers: healthy.
- `/health/live`: `ok`; `/health/ready`: `ok`, database `connected`.
- API-to-PostgreSQL connectivity: passed.
- PostgreSQL cluster ID: **`7690665958609113124`**, unchanged from the Part 11/12 baseline.

## Limitations

- The synthetic suite is a repeatable regression check. Passing does not prove advice suitability, correctness for every user, or regulatory compliance.
- No LLM judge is used. Optional external-provider wording is not independently verified; validation confirms structure, authorization, citations, calculation provenance, and bounds.
- Retrieval remains keyword and structured-query based. It does not establish that every relevant record was found.
- User-entered, imported, stale, and estimated evidence remains labeled and unverified.
- No external model call, emulator test, or physical-device test was performed.
- No trading, purchasing, property-offer, scraping, polling, or autonomous-agent capability was added.
