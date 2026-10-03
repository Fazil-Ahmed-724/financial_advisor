# Part 18 implementation and verification

Verified October 3, 2026 (Asia/Karachi).

Part 18 adds a user-scoped PSX historical research workspace. Migration `20261003_0014` adds reviewed import batches, row previews, and saved historical observations. The development PostgreSQL volume is migrated in place.

## Authorized data workflow

The lifecycle is `CSV upload → bounded UTF-8 parse → row validation → preview → explicit duplicate resolution → atomic commit or cancellation`. Upload idempotency is per user. A saved duplicate must be skipped or explicitly replaced; duplicate rows within one file are invalid. Every batch, preview, observation, history query, calculation, and assistant citation is filtered by authenticated user ID.

The CSV schema is:

| Column | Rule |
| --- | --- |
| `symbol` | 1–20 uppercase letters, numbers, dots, or hyphens |
| `observation_date` | ISO `YYYY-MM-DD`; required |
| `open,high,low,close` | positive decimal, at most four places; consistent OHLC range |
| `volume` | nonnegative whole number |
| `currency` | `PKR` |
| `source` | required provenance; upload-level source is a fallback |
| `adjustment_type` | `raw` or `adjusted` |

All imported evidence is `unverified`. The application does not fetch URLs, infer gaps, merge other users’ data, scrape PSX, call brokers, or poll prices.

## Deterministic calculations

Observations are sorted chronologically. An optional as-of date removes every later row before calculation.

- Period return: `(last close / first close - 1) × 100`.
- Rolling volatility: sample standard deviation of available daily close-to-close returns in the requested lookback, annualized with `sqrt(252) × 100`; unavailable with fewer than two returns.
- Moving average: arithmetic mean of the last requested number of closes; unavailable until the full lookback exists.
- RSI: simple average gain and loss over the requested chronological lookback; unavailable until the full lookback exists and 100 when average loss is zero.
- Output rounding: Decimal `ROUND_HALF_UP` to four decimal places. Binary floating point is not used.
- A gap warning is emitted when adjacent saved observation dates are more than four calendar days apart. Freshness is stale after seven calendar days.

Every result returns the precise observation IDs and dates, provenance, adjustment types, freshness, gap list, formulas, and limitations. Fees, taxes, liquidity, survivorship bias, and unrepresented corporate actions are excluded. Comparisons provide evidence and never assign buy, sell, top-performer, suitability, or guaranteed-return labels.

The assistant retrieves user-owned PSX observations as citations. It can explain their saved values but cannot alter calculations, import data, create alerts, or record trades.

## Main changed files

- `backend/alembic/versions/20261003_0014_psx_research.py`
- `backend/app/models.py`, `psx_service.py`, `schemas_psx.py`, `routes_psx.py`
- `backend/app/assistant_service.py`, `main.py`
- `backend/tests/test_psx.py`, `test_00_migrations.py`
- `mobile/src/app/psx-research.tsx`, `_layout.tsx`, `index.tsx`
- `.env.example`, `compose.yaml`, and `README.md`

## Limitations

Historical evidence is only as complete and accurate as the authorized file. Corporate actions may make raw series incomparable; adjusted series are trusted as labeled by the supplier and are not independently verified. Calendar-gap detection cannot decide whether a gap was a market holiday or missing data. No official PSX validation, live quotes, price polling, alerts, portfolio mutation, prediction, or order execution is included. Native emulator and physical-device testing were not performed.

## Verification results

- Clean disposable database migrated from base through `20261003_0014`.
- Complete Docker backend suite against the final source: **114 passed**, with one upstream Starlette/httpx deprecation warning, in 39.09 seconds. Final focused PSX/assistant calculation-citation tests: **10 passed**.
- Part 13 deterministic offline evaluation: **14/14 passed**, provider disabled and network unavailable.
- Mobile TypeScript and Expo lint: passed.
- Expo dependency compatibility: dependencies current. Expo Doctor: **21/21 passed**.
- Compose configuration: valid.
- Development Alembic state: `20261003_0014 (head)`; `alembic check` reported no pending operations.
- API, PostgreSQL, and notification worker: healthy. `/health/live` returned `ok`; `/health/ready` returned database `connected`.
- PostgreSQL system identifier before and after: `7690665958609113124`. Development user count before and after: `0`; saved PSX observation count remains `0`. The existing development volume and data were preserved.
- `git diff --check`: passed; Windows line-ending notices are informational.
- Physical-device and emulator testing: **not performed**.
