# Part 6 implementation and verification

Verified September 29, 2026 (Asia/Karachi).

## Starting state

The API and PostgreSQL were healthy at `20260929_0004`. The development database contained no users, trades, analyses, or tax rules. PostgreSQL cluster ID was `7690665958609113124`; the persistent volume was not reset or recreated.

## Schema and preservation rules

- `investment_decisions` stores the original user-owned thesis and an optional owned trade or analysis link. There is no update endpoint.
- `decision_reviews` appends reflection, checklist answers, and immutable outcome/process snapshots.
- `audit_events` records decision creation, transaction/analysis links, reviews, tax-rule creation, and report generation.
- Revision `20260929_0005` adds these tables without changing earlier revisions or data.

## Outcome and review logic

Closed positions with complete recorded FIFO history show gross result before fees/tax, fees, realized result before tax, estimated tax, and net estimate. Each applicable tax-rule ID, effective range, rate, and source note is included. Missing configuration produces `null` tax and net results. These are estimates, never official determinations.

Open positions are `unrealized_open`; current market value and unrealized result remain unavailable. Missing links or transaction history are explicit unavailable states. Hypothetical links retain estimate-only status.

The process checklist counts documented yes answers among answered items. Its explanation states that financial results are excluded and that it is neither predictive accuracy nor suitability certification. Profit/loss and process assessment remain separate.

## Endpoints

- `POST /decisions`, `GET /decisions`, `GET /decisions/{id}`
- `POST /decisions/{id}/reviews`
- `GET /audit-events`
- `POST /compliance-reports`

The JSON report contains external trades, FIFO lots/consumptions, realized results, fees, configured tax assumptions, decisions, reviews, and audit history. Dividends are marked unsupported. Every query/export is authenticated and user-scoped. No execution endpoint exists.

## Changed files

- `backend/alembic/versions/20260929_0005_decision_journal.py`
- `backend/app/models.py`, `schemas_decisions.py`, `routes_decisions.py`, `routes_investments.py`, `main.py`
- `backend/tests/test_00_migrations.py`, `test_decisions.py`
- `mobile/src/app/decisions.tsx`, `decision/[id].tsx`, `_layout.tsx`, `index.tsx`, `types.ts`
- `README.md`, `docs/part-6-report.md`

## Commands and results

| Command | Result |
| --- | --- |
| Pre-change Compose/Alembic/count/cluster checks | Healthy; `20260929_0004`; zero investment rows; cluster ID recorded |
| Clean `docker compose --profile test run --build --rm test` | 45 passed; one upstream TestClient deprecation warning |
| Isolated `alembic check` | No new upgrade operations detected |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `docker compose up --build -d --wait` | Existing development database migrated in place; API/database healthy |
| Development `alembic current` / `alembic check` | `20260929_0005 (head)`; no new upgrade operations detected |
| Database connection and health endpoints | Passed; `/health/live` and `/health/ready` HTTP 200 |
| Protected legacy and Part 6 routes without a token | HTTP 401 as designed; authenticated behavior covered by the full suite |
| Post-migration counts and cluster query | Existing rows unchanged at zero; cluster ID still `7690665958609113124` |

## Limitations

- Outcome aggregation uses recorded trades for the linked account and symbol; it does not model broker transfers, corporate actions, or tax-lot methods other than FIFO.
- An open position has no unrealized result until market data exists.
- Tax output depends entirely on user-configured rules and omits statutory details not represented by those rules.
- JSON is the only export format; no signed filing form, CSV, or PDF is produced.
- Native screens still require emulator or physical-phone smoke testing.
- Market feeds, signals, ML, books, broker connectivity, and automatic trading remain out of scope.
