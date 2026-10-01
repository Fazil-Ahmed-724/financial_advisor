# Part 12 implementation and verification

Verified October 1, 2026 (Asia/Karachi).

The baseline was the healthy Part 11 database at `20261001_0010`, PostgreSQL cluster ID `7690665958609113124`. Migration `20261001_0011` adds only user-owned assistant conversations and messages. The development volume is migrated in place and is never reset.

## Architecture and boundaries

The assistant has three layers:

1. A user-scoped retrieval service searches PostgreSQL book passage vectors and structured records from the ledger, holdings, saved sale analyses, tax assumptions, decisions/reviews, property research, and marketplace intelligence.
2. Existing deterministic services and stored analysis snapshots supply amounts and calculations. Generated text never recomputes money, yield, margin, FIFO, tax, or Research Scores.
3. A provider-neutral interface formats the evidence. Deterministic mode is the default and performs no network request. An optional OpenAI-compatible adapter can rewrite the deterministic draft while preserving citations and constraints.

Assistant routes create or delete only their own conversation and message records. They expose no tool capable of writing accounts, journal entries, trades, tax rules, decisions, books, property records, marketplace records, recommendations, or orders. Every retrieval includes `user_id`; conversation reads, writes, and deletes verify ownership.

## Citations, prompts, and evidence

Each answer returns text, citations, calculation/evidence references, freshness labels, limitations, and `deterministic` or `llm` mode. Each citation includes source type, record or passage ID, date when available, a bounded excerpt, an in-app path, and a freshness/estimate label. Insufficient evidence produces no factual substitution and asks the user to add or import the desired data.

The external system prompt states that book passages, documents, listing text, and all retrieved source text are untrusted data. It forbids following embedded instructions, adding facts or calculations, making recommendations, or presenting legal/tax determinations. Provider output missing any required citation marker is discarded and deterministic mode is returned. This check does not independently verify LLM wording.

## Provider and privacy configuration

`ASSISTANT_PROVIDER=disabled` is the safe default. It needs no key, incurs no provider charge, and sends no evidence outside the application.

To opt in, set `ASSISTANT_PROVIDER=openai_compatible` plus `ASSISTANT_PROVIDER_URL`, `ASSISTANT_PROVIDER_MODEL`, and `ASSISTANT_PROVIDER_API_KEY` in the backend environment. Production URLs must use HTTPS. The question and retrieved evidence excerpts are sent to that provider. Users must assess its privacy, retention, residency, and billing terms. Keys are never returned to the client or included in application logs.

Defaults bound storage and context to 20 conversations, 50 messages per conversation, 4,000 characters per question, 8 retrieved records, and 12,000 retrieved characters. Conversation deletion cascades to messages. Retention is user-controlled; no background retention job was added.

## API and mobile

- `POST/GET /assistant/conversations`
- `GET/DELETE /assistant/conversations/{id}`
- `POST /assistant/conversations/{id}/messages`

The Expo screen uses existing secure authentication and Expo Router navigation. It displays conversation history, deterministic/LLM mode, loading/errors, citations, record links, freshness and estimate labels, and limitations. No new native dependency was added.

## Main changed files

- `backend/alembic/versions/20261001_0011_assistant_conversations.py`
- `backend/app/assistant_provider.py`, `assistant_service.py`, `routes_assistant.py`, and `schemas_assistant.py`
- `backend/app/models.py`, `main.py`, and `tests/test_00_migrations.py`
- `backend/tests/test_assistant.py`
- `mobile/src/app/assistant.tsx`, `_layout.tsx`, `index.tsx`, and `types.ts`
- `.env.example`, `compose.yaml`, and `README.md`

## Verification

```powershell
docker compose --profile test rm -sf test-db
docker compose --profile test run --build --rm test
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
```

Results:

- Clean Docker migration from base through `20261001_0011`: passed.
- Complete backend suite: **83 passed**, with one upstream Starlette TestClient deprecation warning.
- Mobile TypeScript and Expo lint: passed.
- `expo install --check`: dependencies up to date.
- Expo Doctor: **21/21 checks passed**.
- Compose configuration: valid.
- Development Alembic state: `20261001_0011 (head)`; `alembic check` found no pending model operations.
- PostgreSQL connectivity: passed.
- `/health/live`: `ok`; `/health/ready`: `ok`, database `connected`.
- API and development database containers: healthy.
- PostgreSQL cluster ID: **`7690665958609113124`**, unchanged from the Part 11 baseline.
- `git diff --check`: passed; line-ending notices are informational for the Windows checkout.

No external model request, emulator test, or physical-device test was performed.

## Limitations

- No external provider output is independently verified. Citation presence shows which stored evidence was supplied; it does not prove a conclusion or recommendation is suitable.
- Deterministic retrieval is keyword/domain based and does not use embeddings or semantic vectors beyond existing PostgreSQL book full-text search.
- External-provider behavior requires the operator's own endpoint, credentials, privacy review, and testing; no paid call was made during verification.
- Stale and user-entered evidence remains unverified. The assistant does not obtain live market data or official tax/legal information.
- Native behavior was not tested on an emulator or physical device.
