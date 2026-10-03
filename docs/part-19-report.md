# Part 19 implementation and verification

Implemented October 3, 2026 (Asia/Karachi).

Part 19 adds evidence-based portfolio exposure and historical scenario analysis. Migration `20261003_0015` adds only `portfolio_instrument_mappings`, an explicit user-owned link between an existing investment-account holding symbol and an imported PSX symbol. Confirmations and changes create immutable `portfolio_mapping_confirmed` audit events.

## Sources of truth and formulas

The latest view calls the existing holdings/FIFO service for quantity, remaining lots, and book cost. Historical scenarios replay existing external BUY and SELL records in chronological FIFO order and ignore every trade after the selected date.

Raw observations are the only valuation prices. For each position:

- observed market value = quantity × last owned raw close on or before the as-of date
- unrealized gain/loss = observed market value − FIFO book cost
- position weight = observed position value / total available observed portfolio value × 100
- concentration HHI = sum of squared available position weights

Positions without a confirmed mapping or eligible raw close remain unavailable. A raw close is fresh through three days, aging through seven days, and stale afterward relative to the analysis date. A stale value is labeled `last_observed_unverified`, never current market value.

Adjusted observations are used only for historical evidence:

- period return = (last adjusted close / first adjusted close − 1) × 100
- annualized volatility = sample standard deviation of adjusted close returns × √252 × 100
- maximum drawdown = minimum(adjusted close / prior running peak − 1) × 100

The requested lookback is 2–252 observations. Outputs use Decimal arithmetic and `ROUND_HALF_UP` to four decimal places for percentages and two places for money. Every result includes trade/lot, mapping, price, adjusted-observation, and tax-rule identifiers as applicable.

## Hypothetical sales and assistant

Current partial-sale estimates call the existing FIFO planner. Historical estimates use only lots reconstructed through the selected date. Gross proceeds use the owned raw close; fees are explicitly entered; the effective-dated user tax rule supplies the gain rate. Without a rule, estimated tax stays unavailable. No loss credit is invented.

The assistant can retrieve user-owned holding, mapping, raw-price, tax, trade-lot, and deterministic portfolio calculation evidence. Numeric calculation references are application-produced and validation prevents provider output from replacing them. Explanations retain stale, unverified, missing-data, methodology, and read-only labels.

No portfolio request writes a ledger entry, trade, lot consumption, tax rule, holding, sale analysis, recommendation, notification, or order.

## Main changed files

- `backend/alembic/versions/20261003_0015_portfolio_exposure.py`
- `backend/app/models.py`, `portfolio_service.py`, `schemas_portfolio.py`, `routes_portfolio.py`
- `backend/app/assistant_service.py`, `main.py`
- `backend/tests/test_portfolio_analysis.py`, `test_00_migrations.py`
- `mobile/src/app/portfolio-analysis.tsx`, `_layout.tsx`, `index.tsx`
- `README.md`

## Data limitations

Imported prices remain user supplied and unverified. Last-observed raw closes are not live executable quotes. Adjusted series are trusted as supplied and may omit dividends or corporate actions. Results may exclude fees, withholding, liquidity, slippage, missing periods, and survivorship effects. Concentration and risk measures describe stored historical evidence and do not establish suitability or predict returns.

## Verification status

Docker was checked before health verification and was unavailable because the Docker Desktop Linux engine pipe did not exist. Therefore the backend Docker suite, Part 13 offline evaluation, live Alembic current/check, container health, API health, cluster identity, and live development row-count checks could not be rerun in this session. The development volume was not reset, recreated, or modified. The repository migration head is `20261003_0015`; it was not applied while Docker was unavailable. The last cluster identity recorded by a previously verified project report is `7690665958609113124`, but a current comparison was not possible.

Checks completed without Docker:

- Python syntax compilation for backend application, tests, and migrations: passed before the final assistant evidence-reference adjustment. A final rerun was attempted but the command runner returned `helper_unknown_error` before starting Python.
- Mobile TypeScript: passed.
- Expo lint: passed.
- Expo dependency validation: passed; dependencies match the installed Expo SDK.
- Expo Doctor: passed, 21/21 checks.
- Compose validation with `docker compose config --quiet`: passed.
- Git whitespace validation: passed before the final report/evidence edits. A final rerun was attempted but the command runner returned `helper_unknown_error` before starting Git.

No emulator or physical-device testing was performed.
