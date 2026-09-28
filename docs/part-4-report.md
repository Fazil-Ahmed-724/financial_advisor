# Part 4 implementation and verification

Verified September 29, 2026 (Asia/Karachi).

## Starting state

The API and PostgreSQL services were healthy, Alembic was at `20260929_0002`, and the persistent PostgreSQL cluster identifier was `7690665958609113124`. The development database contained zero users, accounts, journal entries, and journal lines. The existing volume was neither reset nor recreated.

## Calculation definitions

The dashboard aggregates PKR accounts owned by the authenticated user and uses PostgreSQL `NUMERIC(18,2)` values plus Python `Decimal` arithmetic. Historical balances remain included if an account is later marked inactive.

- Cash and investment accounts are debit-normal, so their raw ledger totals are displayed directly.
- Liability accounts are credit-normal, so their raw totals are negated and normal amounts owed are displayed as positive values.
- Net worth at ledger/book value is cash plus investment book value minus liabilities. Income and expense balances are not counted again because their effect is already present in the balancing asset lines.
- Reserve target is monthly essential expenses multiplied by configured reserve months.
- Protected emergency cash is the smaller of positive cash and the reserve target.
- Investable cash is positive cash minus protected cash and positive liabilities, clamped to zero.

All liabilities are treated as supported current obligations because the current ledger has no due-date or maturity classification. Dashboard responses explicitly say `ledger_book_value` and `market_values_available: false`; no current prices, returns, allocation, or recommendations are inferred.

## Changed files

| Files | Purpose |
| --- | --- |
| `backend/alembic/versions/20260929_0003_financial_profiles.py` | Financial-profile table, constraints, and safe backfill for existing users |
| `backend/app/models.py` | One-to-one user financial profile with numeric expense and month constraints |
| `backend/app/schemas_dashboard.py` | Decimal profile validation and explicit dashboard response contract |
| `backend/app/routes_dashboard.py` | Authenticated profile read/update and ledger-derived dashboard calculations |
| `backend/app/routes_auth.py` | Default financial profile creation during registration |
| `backend/app/main.py` | Dashboard router registration |
| `backend/tests/test_00_migrations.py` | Clean upgrade verification through the Part 4 migration |
| `backend/tests/test_dashboard.py` | Profile validation, reserve arithmetic, ledger signs, isolation, empty state, and book-value tests |
| `mobile/src/types.ts` | Dashboard and financial-profile API types |
| `mobile/src/app/index.tsx` | Dashboard states, book-value labels, reserve form, and focus-based refresh |
| `README.md`, `docs/part-4-report.md` | API, calculation, migration, verification, and limitation documentation |

Earlier migrations were not edited or squashed.

## Commands and results

| Command | Result |
| --- | --- |
| Pre-change Compose health, `alembic current`, counts, and cluster query | API/database healthy; `20260929_0002`; zero finance data; cluster ID recorded |
| `docker compose --profile test run --build --rm test` | 33 passed; one upstream Starlette TestClient deprecation warning |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `npx.cmd expo install --check` | Dependencies up to date |
| `npx.cmd expo-doctor` | 21/21 checks passed |
| `docker compose up --build -d --wait` | Existing development database migrated in place; API/database healthy |
| `docker compose exec -T api alembic current` | `20260929_0003 (head)` |
| `docker compose exec -T api alembic check` | No new upgrade operations detected |
| `/health/live` and `/health/ready` | HTTP 200; readiness reported database connected |
| Unauthenticated `/accounts` and invalid `/auth/login` smoke requests | HTTP 401 as designed; successful auth and finance flows remain covered by the full suite |
| Post-migration counts | Zero users, accounts, entries, lines, and financial profiles |
| Post-migration cluster query | Cluster ID still `7690665958609113124` |

The test profile used its separate temporary PostgreSQL service and did not access the development volume.

## Limitations

- The profile stores one reserve target; it does not classify essential expenses by category.
- Every positive liability is deducted as a current obligation because maturity dates are unavailable.
- Investment and net-worth values are ledger/book values only. Market prices, unrealized returns, and asset allocation are intentionally absent.
- Negative asset balances remain visible in cash and net worth, while reserve protection and investable cash use nonnegative cash.
- Native screens passed TypeScript, lint, Expo dependency, and Expo Doctor checks but still require an Android emulator or physical-phone smoke test.
- Stock trades, FIFO lots, market data, recommendations, tax calculations, push notifications, book ingestion, ML predictions, and broker integration remain out of scope.
