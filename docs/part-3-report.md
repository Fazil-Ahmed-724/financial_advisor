# Part 3 implementation and verification

Verified September 29, 2026 (Asia/Karachi).

## Starting state

The API and PostgreSQL services were healthy. Alembic was at `20260929_0001`, the development database had zero users, and the persistent cluster identifier was `7690665958609113124`.

## Changed files

| Files | Purpose |
| --- | --- |
| `backend/alembic/versions/20260929_0002_accounts_ledger.py` | Accounts, journals, lines, idempotency, constraints, and deferred balance triggers |
| `backend/app/models.py` | SQLAlchemy finance and idempotency models |
| `backend/app/schemas_finance.py` | Normalization, PKR, decimal, timezone, line-count, and balance validation |
| `backend/app/routes_finance.py` | Authenticated account, journal, idempotency, ownership, and balance endpoints |
| `backend/app/main.py` | Finance router registration |
| `backend/tests/test_00_migrations.py` | Full base-to-Part-3 migration verification |
| `backend/tests/test_finance.py` | Account, ledger, ownership, money, idempotency, balances, and rollback tests |
| `mobile/package.json`, `mobile/package-lock.json`, `mobile/app.json`, `mobile/tsconfig.json` | Expo Router and SecureStore configuration |
| `mobile/src/api.ts`, `mobile/src/auth.tsx`, `mobile/src/types.ts`, `mobile/src/components.tsx` | Typed API access, encrypted token storage, shared types, and UI primitives |
| `mobile/src/app/_layout.tsx`, `index.tsx`, `accounts.tsx`, `entry.tsx` | Router, authentication/dashboard, account creation, and entry screens |
| `mobile/App.tsx`, `mobile/index.ts` | Removed after adopting the documented Expo Router entry point |
| `README.md`, `docs/part-3-report.md` | Endpoint examples, behavior, verification, and limitations |

The existing Part 2 migration was not modified or squashed.

## Endpoint behavior

- Account types: `cash`, `investment`, `income`, `expense`, `liability`, `equity`.
- Currency: normalized to `PKR`; other currencies are rejected in Phase 1.
- Money: PostgreSQL `NUMERIC(18,2)` and Python `Decimal`; floats are not used for backend money calculations.
- Balances: natural-sign presentation, so a normal credit balance for income/liability/equity is returned as positive.
- Ownership: every list, balance, and write query includes authenticated `user_id`; composite foreign keys bind each journal line to accounts and entries belonging to the same user.
- Atomicity: entry, both lines, and idempotency response commit together. Validation or database constraint failure rolls back the whole transaction.
- Idempotency: finance writes require a per-user key. Exact replay returns the stored response; changed content or operation returns HTTP 409.

See the root README for complete PowerShell account and opening-balance examples. Income uses cash/investment debit plus income credit. Expense uses expense debit plus cash/investment credit.

## Commands and results

| Command | Result |
| --- | --- |
| Pre-change `docker compose ps` and `alembic current` | API/database healthy; `20260929_0001` |
| Pre-change database counts and `pg_controldata` | Zero users; cluster ID recorded |
| `docker compose --profile test run --build --rm test` | 21 passed; one upstream Starlette TestClient warning |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `npx.cmd expo install --check` | Dependencies up to date |
| `npx.cmd expo-doctor` | 21/21 checks passed |
| `docker compose up --build -d --wait` | Existing development database migrated in place; API/database healthy |
| `docker compose exec -T api alembic current` | `20260929_0002 (head)` |
| `docker compose exec -T api alembic check` | No new upgrade operations detected |
| API database connectivity check | `PostgreSQL connection OK` |
| `/health/live` and `/health/ready` | HTTP 200; database connected |
| Invalid existing `/auth/login` smoke request | HTTP 401 as designed; successful auth remains covered by tests |
| Post-migration counts | Zero users, accounts, entries, and lines |
| Post-migration `pg_controldata` | Cluster ID still `7690665958609113124` |

## Limitations

- Account editing, archival UI, journal reversal, transfers, pagination, reporting periods, and multi-currency conversion are not implemented.
- The API supports only the three two-line workflows described above; arbitrary multi-line journals are intentionally deferred.
- Access-token expiry currently returns an API error in the mobile UI; automatic reauthentication or refresh tokens are not implemented.
- Native mobile screens passed static checks but still require an Android emulator or physical-device smoke test.
- npm reported 13 moderate advisories in the Expo dependency tree after adding Router and SecureStore. `expo install --check` and Expo Doctor passed; no forced breaking downgrade was applied.
- Stock trades, FIFO lots, market values, recommendations, push notifications, books, market data, and broker integration remain out of scope.
