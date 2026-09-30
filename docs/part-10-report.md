# Part 10 implementation and verification

Verified October 1, 2026 (Asia/Karachi).

The starting services were healthy at `20260930_0008`; PostgreSQL cluster ID was `7690665958609113124`. Revision `20261001_0009` was applied in place without resetting the development volume.

## Architecture and migration

`market_locations` provides the market abstraction and seeds the only active market: Pakistan / Sindh / Karachi / PKR / Asia/Karachi. User-owned `marketplace_products` normalize identity. Append-only `marketplace_product_observations` retain prices and demand evidence. `marketplace_sourcing_options` and `marketplace_competition_signals` retain Karachi evidence. `marketplace_product_rankings` stores explainable snapshots, and `marketplace_product_watchlists` stores user-isolated selections.

Matching uses normalized case, whitespace, punctuation, common unit spacing, brand, and model keys. Exact keys return `exact_match`; sufficient token overlap returns `probable_match`; uncertain products remain separate. No LLM performs matching or scoring.

## Scoring

Version `karachi-research-v1` uses demand 25%, Part 9 margin 25%, competition 15%, sourcing 15%, logistics 10%, and evidence confidence 10%. Demand uses only observed sold/review/rating data. Margin reads saved Part 9 net-margin and ROI metrics. Competition inversely scores observed seller/listing counts. Sourcing uses recorded stock status, and logistics uses recorded lead time. Evidence confidence reflects component coverage and freshness.

Missing components are `null`, listed under `missing_inputs`, and reduce confidence. The available-component weighted result is confidence adjusted. Every component includes its score and reason. The result is labeled “Research Score” and includes limitations; it is never called a success score or guarantee.

## APIs and mobile

Authenticated `/api/v1/marketplace` endpoints cover the active market, normalized products, historical observations, sourcing, competition, rankings, filters/sorting, side-by-side comparison, and watchlists. See the README endpoint table.

Expo adds Marketplace Rankings, Product Intelligence Detail, Product Comparison, and Watchlist screens. Karachi is displayed as the fixed current market. Views show available score, margin, ROI, confidence, sourcing, freshness, breakdowns, history, and missing-data warnings. They contain no purchase, listing, advertising, fulfilment, or execution controls.

## Evidence rules

Demand, competition, prices, and sourcing require source classification, reference, observation time, and evidence. Records over 60 days old are visibly stale. Missing values stay unavailable. URLs are stored but never fetched. All queries and referenced entities are scoped to the authenticated user.

## Verification

| Check | Result |
| --- | --- |
| Full clean Docker backend suite | 68 passed; one upstream TestClient warning |
| Clean migration through all revisions | Passed |
| Alembic current / model drift | `20261001_0009 (head)` / no drift |
| Mobile TypeScript / lint | Passed |
| API and PostgreSQL health | Healthy; readiness connected |
| PostgreSQL cluster identity | Unchanged: `7690665958609113124` |

Tests cover the market seed, authentication and isolation, normalization and deterministic matching, append-only price history, staleness, sourcing and competition validation, Decimal price changes, Part 9 margin reuse, missing components, confidence reduction, deterministic ranking snapshots and explanations, filters/sorts, comparisons, watchlist ownership, unsupported sourcing currency, FX behavior through the preserved Part 9 suite, and absence of collection or execution routes.

## Limitations and recommended Part 11

- Evidence remains user entered or supplied through authorized exports/permitted APIs and is not independently verified.
- No explicit product-merge workflow, scheduled import, automated polling, supplier discovery, or demand feed exists.
- The mobile detail and comparison views favor transparent JSON evidence over polished charts.
- Native behavior still needs emulator or physical-device testing.

Recommended Part 11: build reviewed CSV/import adapters with mapping previews, explicit product merge/split controls and audit history, saved filter presets, and improved native evidence-entry and comparison presentation. Keep automated scraping, purchasing, listing, advertising, fulfilment, and autonomous financial decisions out of scope.
