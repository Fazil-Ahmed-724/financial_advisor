# Part 9 implementation and verification

Verified September 30, 2026 (Asia/Karachi).

The starting development services were healthy at Alembic `20260930_0007`, with PostgreSQL cluster ID `7690665958609113124`. Migration `20260930_0008` was applied in place without resetting the development database or volume.

## Design and sources

The opportunity registry now includes `marketplace_resale` and adapters for Daraz, Temu, SHEIN, and Other. Adapters accept user entry, authorized exports, or permitted API data. They normalize supplied URLs only for provenance and deduplication and perform no network retrieval.

Source observations, immutable estimates, and actual outside-app outcomes use separate tables. Listings retain platform, product/SKU/source ID, URL, observation date, currency, source price, attributes, evidence, expected Karachi selling price, and local channel. Outcomes retain their original estimate snapshot and report actual values and assumption differences. Property, securities, and investment-decision records remain separate.

## Calculations

Calculations use `Decimal`, PostgreSQL `NUMERIC`, and exact decimal strings:

- Landed cost = converted source cost + shipping + customs + conversion fee.
- Break-even = landed cost + selling/payment fees + packaging + delivery + other costs + returns/damage/unsold allowances.
- Gross margin = expected selling price - landed cost.
- Net margin = expected selling price - break-even.
- Net margin percentage = net margin / selling price × 100.
- Inventory cash ROI = net margin / break-even × 100.

All eleven cost categories must be supplied; zero is valid. Non-PKR data requires a rate, observation timestamp, and source. Missing required assumptions return `unavailable_missing_inputs` and null metrics. Results retain formulas, inputs, missing fields, source dates, evidence, limitations, and analyzer version.

Actual net result is revenue minus purchase cost, other costs, sales fees, and return costs. Forecast error compares actual net result with estimated net margin across purchased quantity. Outcomes use `success_label: not_assigned`.

## Endpoints

| Method | Path |
| --- | --- |
| `POST`, `GET` | `/marketplace/listings` |
| `POST` | `/opportunities/analyze/marketplace_resale/margin` |
| `GET` | `/marketplace/analyses` |
| `POST`, `GET` | `/marketplace/outcomes` |

All routes require authentication. Writes require idempotency keys, and queries and referenced records are user scoped.

## Changed files

- `backend/alembic/versions/20260930_0008_marketplace_resale.py`
- `backend/app/models.py`, `schemas_marketplace.py`, `routes_marketplace.py`, `routes_opportunities.py`, `main.py`
- `backend/app/routes_dashboard.py`, `schemas_dashboard.py`
- `backend/tests/test_marketplace.py`, `test_opportunities.py`, `test_dashboard.py`, `test_00_migrations.py`
- `mobile/src/app/marketplace.tsx`, `inventory.tsx`, `_layout.tsx`, `index.tsx`, and `mobile/src/types.ts`
- `README.md` and this report

## Verification

| Command | Result |
| --- | --- |
| `docker compose --profile test rm -sf test-db` | Recreated only the disposable test database |
| `docker compose --profile test run --build --rm test` | 61 passed; one upstream TestClient warning |
| `npm.cmd run typecheck` / `npm.cmd run lint` | Passed |
| `docker compose up --build -d --wait` | Development migration applied in place; services healthy |
| `docker compose exec api alembic current` / `alembic check` | `20260930_0008 (head)`; no model/schema drift |
| Health and database connectivity | Passed |
| PostgreSQL identity | Unchanged at `7690665958609113124` |

Tests cover adapters and unknown platforms, provenance, source times, staleness, deduplication, idempotency, isolation, exact cost/margin/ROI math, dated currency conversion, missing inputs, immutable estimate snapshots, outcomes, confirmed inventory separation, all earlier modules, and absence of scraping, purchasing, listing, advertising, fulfilment, or execution routes.

## Limitations

- Source data, exchange rates, fees, customs, demand, and outcomes are not independently verified.
- No marketplace API integration or automated collection is included.
- The starter mobile estimate form applies one editable value to each cost category; the API supports each independently.
- Confirmed inventory is user valued and reported separately. Cash movement requires an explicit balanced ledger entry.
- Native behavior still needs emulator or physical-device testing.
