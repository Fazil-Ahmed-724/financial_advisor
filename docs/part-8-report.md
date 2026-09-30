# Part 8 implementation and verification

Verified September 30, 2026 (Asia/Karachi).

The starting API and PostgreSQL services were healthy at Alembic `20260930_0006`; PostgreSQL cluster ID was `7690665958609113124`. The development database contained no users, accounts, or books. Its volume was not reset or recreated.

## Design

`OpportunityRegistry` separates domain analyzers and data-source adapters from shared persistence. Each analysis stores its domain, source/reference, observation and calculation times, input snapshot, source evidence, assumptions, calculated metrics, optional recommendation, limitations, and analyzer version. Property-specific typed rows retain comparable and yield fields for structured querying. Unknown domains or analyzer types fail clearly.

The only registered domain is `karachi_real_estate`. Its `manual_authorized` adapter accepts user-entered or authorized-export data and never performs network retrieval. HTTP(S) source URLs, including Zameen URLs, are normalized only for provenance and deduplication. Per-user partial unique indexes deduplicate canonical URLs and source IDs. Records over 90 days old are marked stale.

Area comparisons convert only explicit units: square feet, square yards, 225-square-foot marla, 272.25-square-foot marla, 4,500-square-foot kanal, and 5,445-square-foot kanal. Ambiguous `marla` or `kanal` inputs are rejected. Comparable analysis filters by purpose, property type, area name, normalized area, and asking range. It reports count/range and reports a median only with at least three records. Evidence includes the exact listing IDs and source dates. Asking prices remain labeled unverified rather than transaction prices.

Yield calculations use Python `Decimal`, PostgreSQL `NUMERIC`, and exact decimal strings in stored JSON/API results. Gross annual yield is annual rent divided by purchase price. Net yield is unavailable unless both annual expense assumptions and property tax are supplied. Included and excluded costs are explicit; the application invents no maintenance, vacancy, tax, legal, or transaction-cost facts.

Property records remain separate from the balanced ledger. Research values cannot change cash, investment book value, reserves, or investable cash. The dashboard retains ledger-only net worth and exposes a separate total including only user-owned, explicitly confirmed property valuations.

## Changed files

- `backend/alembic/versions/20260930_0007_opportunity_property.py`
- `backend/app/models.py`, `opportunity_registry.py`, `schemas_opportunities.py`, `routes_opportunities.py`, `main.py`
- `backend/app/routes_dashboard.py`, `schemas_dashboard.py`
- `backend/tests/test_opportunities.py`, `test_00_migrations.py`, `test_dashboard.py`
- `mobile/src/app/property.tsx`, `_layout.tsx`, `index.tsx`, and `mobile/src/types.ts`
- `README.md` and this report

## Verification

| Command | Result |
| --- | --- |
| `docker compose --profile test rm -sf test-db` | Recreated only the disposable test database |
| `docker compose --profile test run --build --rm test` | 55 passed; one upstream TestClient deprecation warning |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `npx.cmd expo install --check` / `npx.cmd expo-doctor` | Dependencies current; 21/21 checks passed |
| `docker compose up --build -d --wait` | Development services healthy; migration applied in place |
| `docker compose exec api alembic current` / `alembic check` | `20260930_0007 (head)`; no schema drift |
| Health and database connection checks | Passed |
| PostgreSQL identity after migration | Unchanged at `7690665958609113124` |

Backend tests cover registry discovery and unknown domains, Karachi and unit validation, provenance, stale data, URL deduplication, idempotency, user isolation, filtering and explicit unit conversion, insufficient and sufficient comparable samples, range/median math, gross/net yield and missing assumptions, dashboard separation, clean migrations, all prior finance/auth/book behavior, and absence of scraping, offer, order, or broker routes.

## Limitations

- Listing entry is manual or from a user-authorized export. No website crawling, automated Zameen collection, or third-party listing API is implemented.
- Asking prices are unverified. No confirmed transaction feed, title/legal verification, inspection, neighborhood scoring, or current market valuation exists.
- Property tax and operating costs must be supplied by the user; estimates are not legal or tax advice.
- Comparable quality depends on the entered data and simple typed filters. It does not assert that properties are truly equivalent.
- The mobile workflow needs an emulator or physical-phone smoke test.
- No recommendation, negotiation, offer, order, payment, or broker execution capability exists.
