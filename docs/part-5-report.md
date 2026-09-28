# Part 5 implementation and verification

Verified September 29, 2026 (Asia/Karachi).

## Starting state and boundary

The API and PostgreSQL were healthy at Alembic `20260929_0003`. The development database contained no users, accounts, or journal entries, and its persistent cluster identifier was `7690665958609113124`. The volume was not reset or recreated.

The application records BUY and SELL transactions already completed outside the app. No route, model, dependency, or mobile control connects to a broker or submits, routes, or executes an order. Hypothetical sale results are stored calculations labeled `estimate_only` and `order_placed: false`.

## Ledger and FIFO rules

- BUY: debit investment and credit cash by execution value plus purchase fees. That total becomes the lot's original book cost.
- SELL: consume open lots by acquisition date, creation time, and ID. Credit investment by FIFO book cost and debit cash by gross proceeds less sale fees. The balancing difference is realized income for a gain or expense for a loss.
- Full-lot consumption takes the lot's exact remaining cost. Partial consumption allocates remaining cost proportionally and rounds half-up to PKR cents.
- Holdings and lots explain journal investment book value. The dashboard continues to aggregate journal lines only, so it never double-counts lot values.
- Quantity, execution-price, and currency precision are PostgreSQL `NUMERIC(24,8)`, `NUMERIC(18,4)`, and `NUMERIC(18,2)`. Python calculations use `Decimal`.

An external sale requires sufficient quantity in the user's selected investment account and acquired by the sale date. Trades should be recorded chronologically; an subsequently entered backdated buy does not revise a committed sale.

## Tax and hypothetical analysis

Tax rules are user-owned and effective-dated, with a percentage rate, source note, and optional loss-treatment note. The project contains no built-in Pakistani tax rate. The latest applicable configured rule is selected by effective date.

The estimate snapshots the user-entered price, quantity, fees, calculation date, FIFO allocations, applicable rule, assumptions, excluded items, and calculation timestamp. With no rule, tax is `null` and labeled `not_configured`. For a configured positive estimate, the rate applies to gross proceeds minus FIFO cost and entered fees. For a loss, estimated tax is zero and status explicitly says no automatic loss credit; an optional treatment note remains separate. Analysis never consumes lots or posts ledger lines.

## Changed files

| Files | Purpose |
| --- | --- |
| `backend/alembic/versions/20260929_0004_investment_fifo.py` | Trade, lot, consumption, tax-rule, analysis tables and trade journal kind |
| `backend/app/models.py` | Decimal investment, FIFO, tax, and analysis models |
| `backend/app/schemas_investments.py` | Input normalization, precision, dates, and explicit result boundaries |
| `backend/app/routes_investments.py` | External trade recording, FIFO, holdings, tax rules, and non-mutating analysis |
| `backend/app/main.py` | Investment router registration |
| `backend/tests/test_00_migrations.py`, `test_investments.py` | Clean migration and investment behavior tests |
| `mobile/src/app/trade.tsx` | Completed external transaction form |
| `mobile/src/app/holdings.tsx` | Holdings and FIFO lot browser |
| `mobile/src/app/analysis.tsx` | User-priced hypothetical sale analysis |
| `mobile/src/app/_layout.tsx`, `index.tsx`, `types.ts` | Navigation, entry points, and API contracts |
| `README.md`, `docs/part-5-report.md` | Rules, endpoints, checks, and limitations |

Earlier migrations were not edited or squashed.

## Endpoints

- `POST /investment-trades`, `GET /investment-trades`
- `GET /holdings`
- `POST /tax-rules`, `GET /tax-rules`
- `POST /sale-analyses`, `GET /sale-analyses`

All require authentication. POST endpoints require `Idempotency-Key` and scope data to the authenticated user.

## Commands and results

| Command | Result |
| --- | --- |
| Pre-change `docker compose ps`, `alembic current`, row counts, cluster query | Services healthy; `20260929_0003`; zero user/ledger rows; cluster ID recorded |
| `docker compose --profile test run --build --rm test` | 39 passed; one upstream Starlette TestClient deprecation warning |
| Isolated `alembic check` | No new upgrade operations detected |
| `npm.cmd run typecheck` | Passed |
| `npm.cmd run lint` | Passed |
| `docker compose up --build -d --wait` | Existing development database migrated in place; API and database healthy |
| Development `alembic current` / `alembic check` | `20260929_0004 (head)`; no new upgrade operations detected |
| API database connectivity, `/health/live`, `/health/ready` | Passed; health HTTP 200 and database connected |
| Protected auth, ledger, dashboard, trade, and holding route smoke checks | HTTP 401 without a token as designed; authenticated success paths covered by the full suite |
| Post-migration rows and cluster query | Existing rows remained zero; cluster ID still `7690665958609113124` |

## Limitations

- Prices are user-entered execution or hypothetical values; there is no live market feed or market-value calculation.
- Tax results are only as reliable as the user's configured effective-dated rule and source note; withholding, holding-period rules, exemptions, filing status, and other taxes are excluded.
- Backdated trade insertion does not recalculate later recorded sales; record external statements chronologically.
- Corporate actions, transfers between brokers, dividends, splits, short selling, lot selection other than FIFO, and trade edits/reversals are not implemented.
- Native mobile screens passed static checks but still require emulator or physical-phone smoke testing.
- Push notifications, books, ML predictions, recommendations, and broker connectivity remain out of scope.
