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

Docker Desktop was initially stopped and was started for this verification. Docker automatically restored the previously created development containers. Before any explicit migration command, the database reported cluster identity `7690665958609113124`, exactly matching the recorded value. No volume was deleted, reset, or recreated.

The restored API image still contained repository head `20261003_0014`. After rebuilding the existing images from the current tree, the existing migration was applied in place:

```powershell
docker compose -f compose.yaml build api notification-worker test
docker compose -f compose.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml up -d --no-deps api notification-worker
```

Alembic upgraded `20261003_0014 -> 20261003_0015`. The final live checks report `20261003_0015 (head)` and `No new upgrade operations detected` from `alembic check`.

Backend and assistant evaluation:

```powershell
docker compose -f compose.yaml --profile test run --rm test
docker compose -f compose.yaml --profile test run --rm `
  -v "${PWD}\docs\evaluations:/reports" test `
  python -m evaluation.runner `
  --json /reports/part-13-evaluation.json `
  --markdown /reports/part-13-evaluation.md
```

- Complete backend suite: 119 passed, one third-party Starlette/httpx deprecation warning, in 29.15 seconds.
- Part 13 offline evaluation: 14/14 passed, provider disabled, network access false, zero failed cases.
- An initial `pytest -q` override failed collection because invoking the installed pytest script omitted `/app` from Python's import path. Rerunning the project-configured `python -m pytest` command passed; no code change was required.

Live database and service verification:

```powershell
docker compose -f compose.yaml exec -T api alembic current
docker compose -f compose.yaml exec -T api alembic check
docker compose -f compose.yaml exec -T db psql -U wealth_local -d wealth_manager -At -c "SELECT system_identifier FROM pg_control_system()"
curl.exe --fail --silent --show-error http://127.0.0.1:8000/health/live
curl.exe --fail --silent --show-error http://127.0.0.1:8000/health/ready
docker compose -f compose.yaml ps
```

- Cluster identity after migration: `7690665958609113124`, unchanged.
- Development row counts after migration: users 0, investment trades 0, PSX observations 0, portfolio mappings 0. The new table exists and no pre-existing domain rows were removed.
- `/health/live`: `{"status":"ok"}`.
- `/health/ready`: `{"status":"ok","database":"connected"}`.
- API, PostgreSQL, and notification worker: healthy. Development services were left running.

Mobile and repository checks:

```powershell
cd mobile
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo install --check
npx.cmd expo-doctor
cd ..
git diff --check
git status --short
```

- TypeScript: passed.
- Expo lint: passed.
- Expo dependency validation: dependencies up to date.
- Expo Doctor: 21/21 checks passed.
- Compose validation with `docker compose -f compose.yaml config --quiet`: passed.
- `git diff --check`: passed after the report update; the only output was an expected Windows LF-to-CRLF conversion warning for this Markdown file.
- Final Git status contains one intended modification: `docs/part-19-report.md`. Regenerated evaluation outputs were byte-for-byte unchanged.

No emulator or physical-device testing was performed.
