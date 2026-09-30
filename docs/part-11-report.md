# Part 11 implementation and verification

Verified October 1, 2026 (Asia/Karachi).

The development PostgreSQL volume was preserved. The starting Alembic head was `20261001_0009`, PostgreSQL was healthy, and cluster ID was `7690665958609113124`. Revision `20261001_0010` adds reviewed imports, product aliases, merge/split audit events, saved presets, and product archive/merge metadata.

## Import lifecycle and security

Authenticated CSV and JSON imports follow `upload → safe parse → column mapping → validation → preview → duplicate detection → explicit row action → atomic commit`. A row can create a product, attach to an owned existing product, be skipped, or remain under review. Invalid or uncertain rows block commit until the user explicitly resolves or skips them. A failed commit rolls back all records in that batch.

Accepted imports are product observations, sourcing options, and competition observations. Imported ranking or margin output is unsupported and never trusted. File extensions and media types are allowlisted, filenames are reduced to their basename, UTF-8 parsing is bounded, and configurable size/row limits apply. Every query, match candidate, reassignment, preset, export, and audit record is scoped to the authenticated user. CSV exports prefix spreadsheet-formula characters.

## Identity, history, and analysis

Matching uses the Part 10 normalized key plus user-owned aliases. Exact, probable, ambiguous, and unmatched states remain deterministic. Merge moves evidence to the selected target, retains the old name as an alias, archives the source, preserves ranking snapshots, and records the moved IDs. Split creates a new product and reassigns explicitly selected owned evidence. Both operations create immutable audit snapshots.

Chronological history combines product creation, aliases, imported rows, observations, sourcing, competition, ranking snapshots, merge/split events, and current watchlist state. Saved research presets validate supported filters and sort fields before storage and execution. Batch ranking has a configured maximum and returns per-product success or failure, so one unusable product does not hide the other results.

Freshness is defined once in `marketplace_policy.py`: marketplace price and competition are fresh through 7 days and aging through 14; demand and sourcing are fresh through 14 and aging through 28. Data quality reports stale evidence, unresolved matching, missing fields, warnings, and a readiness state. Research Scores remain explainable evidence summaries, not success predictions.

## Mobile experience

Expo now includes CSV/JSON selection, import history, preview and match review, explicit row actions, and commit feedback. Product detail shows data quality and chronological audit history and provides validated price, sourcing, and competition evidence forms. Comparison uses labeled fields for Research Score, confidence, price, sourcing, competition, and margin rather than raw JSON. No screen can scrape, purchase, publish listings, advertise, fulfil, or execute a financial transaction.

## Endpoint and file summary

New API groups cover imports and previews, row actions and commit/cancel, product merge/split/history/data-quality, preset CRUD/run, bounded batch ranking, and scoped CSV/JSON exports. The README contains the endpoint table and environment settings.

Primary implementation files:

- `backend/alembic/versions/20261001_0010_marketplace_import_review.py`
- `backend/app/marketplace_policy.py`
- `backend/app/routes_marketplace_review.py`
- `backend/app/models.py`, `schemas_intelligence.py`, `routes_intelligence.py`, and `main.py`
- `backend/tests/test_marketplace_review.py` and the migration test
- `mobile/src/app/marketplace-import.tsx`, `match-review.tsx`, `product/[id].tsx`, and `product-compare.tsx`
- `.env.example`, `compose.yaml`, and `README.md`

## Verification

The final results are recorded after the commands below:

```powershell
docker compose --profile test rm -sf test-db
docker compose --profile test run --build --rm test
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
Set-Location ..
docker compose up --build -d --wait
docker compose exec api alembic current
docker compose exec api alembic check
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Results: the clean Docker migration and complete backend suite passed with **77 tests** and one upstream Starlette TestClient deprecation warning. Mobile TypeScript and Expo lint passed. Compose configuration validated, the development database migrated in place to `20261001_0010 (head)`, `alembic check` found no model drift, PostgreSQL connectivity passed, and both health endpoints returned `ok`. The API and database containers are healthy. The PostgreSQL cluster identity remains **`7690665958609113124`**, confirming the development volume was preserved.

## Limitations and recommended Part 12

- Evidence still depends on user-entered data, authorized exports, or separately documented permitted APIs; the app does not verify a marketplace claim independently.
- Merge and split are explicit API/mobile review operations and have no automatic undo. Audit history preserves what changed.
- Native import behavior still needs emulator and physical-device testing.
- Exports are requested from the API; a native share/download workflow is not included.

Recommended Part 12: add scheduled ingestion only for documented permitted APIs, background job observability, and richer native preset/export controls after source terms and credentials are available. Keep scraping, automated purchasing, marketplace listing, advertising, fulfilment, and autonomous financial decisions out of scope.
