# Personal AI Wealth Manager

Phase 1, Parts 1–16: Dockerized FastAPI and PostgreSQL, authentication, a balanced PKR ledger, investment records, decision and book-learning tools, property and marketplace research, reviewed imports, a cited read-only research assistant, and opt-in multi-device informational notifications.

## Initial inspection

The supplied repository contained only `.git`, with no commits or tracked files. Parts 1–8 established the environment, authentication, ledger and reserve dashboard, external trade records and FIFO cost basis, decision reviews, a private cited book library, and user-supplied Karachi property research. The app cannot submit, route, or execute an order. Live market values, automated listing collection, recommendations, notifications, and broker integrations are not implemented. Tables are created only by Alembic migrations; application code never calls `Base.metadata.create_all()`.

## Requirements

- Windows with Docker Desktop running Linux containers (WSL 2 backend recommended).
- Node.js 24 LTS and npm for the Expo SDK 57 starter.
- Expo Go compatible with the project SDK on a physical phone, or an Android Studio emulator. No local Python or PostgreSQL installation is needed.

Use `npm.cmd` and `npx.cmd` in PowerShell to avoid execution-policy errors from the `.ps1` wrappers.

## Backend: Windows PowerShell

Run from the repository root. Copy the environment file once; keep existing values on later runs.

```powershell
Copy-Item .env.example .env
# Replace AUTH_SECRET before using a shared environment. One way to generate it:
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$secret = [Convert]::ToBase64String($bytes)
(Get-Content .env) -replace '^AUTH_SECRET=.*$', "AUTH_SECRET=$secret" | Set-Content .env
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

The readiness response must contain `status: ok` and `database: connected`. It performs a real `SELECT 1` against PostgreSQL using the API's configured credentials. `/health/live` only checks the API process; `/health/ready` returns HTTP 503 if the database is unavailable. API documentation: <http://localhost:8000/docs>.

The API container runs `alembic upgrade head` before starting Uvicorn. If a migration fails, the API does not start.

## Database migrations

Run migrations through the API image so PostgreSQL stays private to the Compose network:

```powershell
# Apply all pending migrations (also happens on normal API startup)
docker compose run --rm api alembic upgrade head

# Show the applied revision
docker compose run --rm api alembic current

# Verify that SQLAlchemy models do not require another migration
docker compose run --rm api alembic check

# Create a reviewed migration after changing models in a future part
docker compose run --rm api alembic revision --autogenerate -m "describe change"
```

Review every generated migration before applying it. `downgrade` can destroy data and is intentionally omitted from the normal development workflow. Revisions `20260929_0001` through `0003` create users, the ledger, and financial profiles. Revision `20260929_0004` adds investment/FIFO records and tax assumptions. Revision `20260929_0005` adds immutable decision snapshots, append-only reviews, and audit events.

The test profile uses a separate `test-db` PostgreSQL service with a temporary in-memory data directory. Its command downgrades to the empty base and upgrades to `head` before every test run. It does not connect to the development database or mount `postgres_data`.

## Authentication API

Passwords must contain 12–128 characters and are stored as Argon2 hashes. Emails are validated and normalized to lowercase. Access tokens are signed HS256 JWTs with a 15-minute default lifetime. Protected requests validate the signature, expiry, token type, and that the referenced user still exists.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account and return the user plus access token |
| `POST` | `/auth/login` | Verify credentials and return an access token |
| `GET` | `/auth/me` | Protected endpoint returning the authenticated user |

PowerShell example:

```powershell
$registration = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/auth/register `
  -ContentType 'application/json' `
  -Body (@{ email = 'person@example.com'; password = 'correct horse battery staple' } | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($registration.token.access_token)" }
Invoke-RestMethod -Uri http://localhost:8000/auth/me -Headers $headers

$login = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/auth/login `
  -ContentType 'application/json' `
  -Body (@{ email = 'person@example.com'; password = 'correct horse battery staple' } | ConvertTo-Json)
```

Only send credentials and bearer tokens over HTTPS outside local development. There are no refresh tokens, logout/revocation, password reset, email verification, rate limiting, or mobile authentication screens yet.

## Accounts and balanced journal API

All routes require a bearer token and scope every query to that user. Phase 1 supports PKR only.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/accounts` | Create a cash, investment, income, expense, liability, or equity account |
| `GET` | `/accounts` | List the authenticated user's accounts |
| `GET` | `/accounts/balances` | Return natural-sign balances for the user's accounts |
| `POST` | `/journal-entries` | Record an opening, income, or expense entry |
| `GET` | `/journal-entries` | List the user's journal entries and signed lines |

Finance write routes require `Idempotency-Key`. Repeating the same key and canonical request returns the original result; changing the request or endpoint while reusing that key returns HTTP 409. Use a new UUID per intended operation and retain it when retrying an uncertain network request.

Journal line amounts are decimal strings with at most two decimal places. Positive values are debits and negative values are credits; every request must contain exactly two nonzero lines totaling `0.00`. PostgreSQL `NUMERIC(18,2)`, composite ownership foreign keys, and deferred constraint triggers independently prevent partial, cross-user, one-line, or unbalanced commits.

Supported patterns:

- Opening asset: debit cash/investment, credit equity.
- Opening liability: credit liability, debit equity.
- Income: debit cash/investment, credit income.
- Expense: debit expense, credit cash/investment.

PowerShell example after obtaining `$headers` from the authentication example:

```powershell
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$cash = Invoke-RestMethod -Method Post -Uri http://localhost:8000/accounts `
  -Headers $headers -ContentType 'application/json' `
  -Body (@{ name = 'Main Cash'; type = 'cash'; currency = 'PKR' } | ConvertTo-Json)

$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$equity = Invoke-RestMethod -Method Post -Uri http://localhost:8000/accounts `
  -Headers $headers -ContentType 'application/json' `
  -Body (@{ name = 'Opening Equity'; type = 'equity'; currency = 'PKR' } | ConvertTo-Json)

$entry = @{
  kind = 'opening'
  description = 'Opening cash balance'
  occurred_at = (Get-Date).ToUniversalTime().ToString('o')
  lines = @(
    @{ account_id = $cash.id; amount = '10000.00' }
    @{ account_id = $equity.id; amount = '-10000.00' }
  )
}
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method Post -Uri http://localhost:8000/journal-entries `
  -Headers $headers -ContentType 'application/json' -Body ($entry | ConvertTo-Json -Depth 4)

Invoke-RestMethod http://localhost:8000/accounts/balances -Headers $headers
```

## Emergency reserve and dashboard API

All routes require a bearer token and return PKR decimal values as strings. The profile accepts nonnegative monthly essential expenses with at most two decimal places and reserve months from `0` through `24`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/financial-profile` | Read monthly essential expenses and reserve months |
| `PUT` | `/financial-profile` | Update the authenticated user's reserve settings |
| `GET` | `/dashboard` | Return ledger-derived cash, liabilities, reserve, and book-value totals |

Dashboard signs follow the Part 3 ledger. Cash and investment assets use their debit-positive raw balances. Liability accounts normally have credit balances, so the API negates their raw totals and presents amounts owed as positive values. Income and expense accounts are already reflected through their balancing asset lines and are not added again. Therefore:

- `net_worth_book_value = cash_balance + investment_book_value - liability_balance`
- `reserve_target = monthly_essential_expenses × reserve_months`
- `protected_emergency_cash = min(max(cash_balance, 0), reserve_target)`
- `investable_cash = max(max(cash_balance, 0) - protected_emergency_cash - max(liability_balance, 0), 0)`

All recorded liabilities are treated as current obligations in this phase because the ledger does not yet classify maturity dates. Investment and net-worth values are explicitly ledger/book values. The response includes `valuation_basis: ledger_book_value` and `market_values_available: false`; it does not estimate current market prices, returns, or allocation.

```powershell
$profile = @{
  monthly_essential_expenses = '50000.00'
  reserve_months = 6
} | ConvertTo-Json

Invoke-RestMethod -Method Put -Uri http://localhost:8000/financial-profile `
  -Headers $headers -ContentType 'application/json' -Body $profile

Invoke-RestMethod -Uri http://localhost:8000/dashboard -Headers $headers
```

## External investment records and FIFO analysis

These routes require authentication. All POST routes require `Idempotency-Key`. The application records completed external transactions and performs estimates; it has no broker connector or order-execution route.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/investment-trades` | Record or list completed external BUY/SELL transactions |
| `GET` | `/holdings` | List quantities, remaining FIFO book cost, realized gain/loss, and open lots |
| `POST`, `GET` | `/tax-rules` | Configure or list user-supplied, effective-dated gain-tax assumptions |
| `POST`, `GET` | `/sale-analyses` | Store or review estimate-only hypothetical FIFO sale calculations |

A BUY debits investment book value for execution value plus purchase fees and credits cash. A SELL consumes eligible lots by acquisition date, then creation order and lot ID. Full-lot consumption uses the exact remaining cost; partial consumption allocates remaining cost proportionally and rounds half-up to PKR cents. Sale fees reduce proceeds. The journal credits investment by FIFO cost and posts the resulting realized gain or loss to automatically created user-owned income or expense accounts. Holdings are explanatory records and are never added to dashboard totals, preventing double-counting.

Trade quantities support eight decimal places, prices four, and PKR amounts two. Completed trades cannot be future-dated. External sales require sufficient quantity acquired by the sale date. Record trades chronologically because a later-entered backdated purchase does not recalculate an already recorded sale.

Hypothetical analysis does not consume lots or change ledger balances. Gross profit/loss is gross proceeds minus FIFO cost. Net profit/loss also subtracts entered fees and configured estimated tax. No Pakistani rate is supplied by the application. With no applicable rule, `estimated_tax` is `null` and status is `not_configured`. A configured rate applies only to a positive estimate after fees; a loss produces zero estimated tax and never assumes a credit or refund. Any user-entered loss-treatment note is shown separately. Each result stores FIFO allocations, assumptions, exclusions, calculation time, `estimate_only`, and `order_placed: false`.

## Decision journal and compliance records

Decision records preserve the original rationale and cannot be edited. A record may link to one owned external trade or hypothetical analysis. Later reflection is appended through separate review records.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/decisions` | Create immutable reasoning snapshots or list them |
| `GET` | `/decisions/{id}` | View original thesis, measured outcome, and review history |
| `POST` | `/decisions/{id}/reviews` | Append a post-decision review and checklist snapshot |
| `GET` | `/audit-events` | List the user's append-only audit history |
| `POST` | `/compliance-reports` | Generate an idempotent, user-scoped JSON export |

Closed positions report FIFO realized results, fees, applicable user-configured tax estimates, net estimates, and the exact tax-rule IDs/effective dates used. Missing tax configuration remains unavailable rather than zero. Open positions are labeled unrealized, with unrealized profit/loss unavailable because no market price exists. Incomplete histories are labeled unavailable.

The five-item review checklist covers pre-trade thesis, risk review, concentration, recorded limits, and adherence to plan. Its explainable count includes only answered process questions. Financial profit or loss never changes that process count and does not label a decision good or bad. Reports are informational records, not official tax determinations. Dividends are explicitly marked unsupported because the ledger does not yet record them.

```powershell
# Follow logs (Ctrl+C stops following, not the services)
docker compose logs --follow --tail 100 api db

# Rebuild and start after backend code/dependency changes
docker compose up --build -d --wait

# Stop services while retaining containers and database data
docker compose stop

# Start again
docker compose up -d --wait

# Remove containers and network, retaining database data
docker compose down
```

PostgreSQL 17 stores data in the named `postgres_data` volume, mounted at `/var/lib/postgresql/data`. Normal `stop`, `down`, and rebuild operations retain data. Do not add `--volumes` to `down` unless intentionally deleting the local database. Existing volumes retain their original database/user/password; changing `.env` does not change credentials inside an initialized database.

PostgreSQL has no published host port. The API connects to `db:5432` on the Compose network. Compose waits for PostgreSQL's health check before starting the API; the API's own health check includes database connectivity. The optional `test` service is excluded from normal startup.

## Environment and secrets

Root `.env` supplies database settings, API binding, `APP_ENV`, `AUTH_SECRET`, and `ACCESS_TOKEN_MINUTES`. The supplied database password and signing secret are intentionally public, local-only examples. Choose unique values before initializing a shared environment. These containers are a development environment, not a production deployment.

The backend reads connection settings and signing secrets from environment variables; there are no credential defaults in Python. `.env` files are ignored by Git and excluded from the Docker build context. Health and authentication errors do not expose secrets. The container runs FastAPI as a non-root user. Startup fails if `AUTH_SECRET` is missing or shorter than 32 characters; `APP_ENV=production` also rejects the published local/test example secrets. Access-token lifetimes must be 1–60 minutes.

`mobile/.env` contains only `EXPO_PUBLIC_API_URL`. Expo embeds `EXPO_PUBLIC_*` values in the application: never put passwords, tokens, or other secrets in them.

## Mobile: outside Docker

In a separate PowerShell window:

```powershell
Set-Location mobile
Copy-Item .env.example .env
npm.cmd ci
npm.cmd start
# Press a for the running Android emulator, or scan the QR code with Expo Go.
```

Set `EXPO_PUBLIC_API_URL` according to the device:

| Client | API base URL | Root `.env` API_BIND_HOST |
| --- | --- | --- |
| Windows host / PowerShell | `http://localhost:8000` | `127.0.0.1` |
| Android Studio emulator | `http://10.0.2.2:8000` | `127.0.0.1` |
| Physical phone on the same Wi-Fi | `http://<PC-LAN-IPv4>:8000`, for example `http://192.168.1.20:8000` | `0.0.0.0` |

For a phone, use `ipconfig` to find the PC's active Wi-Fi/Ethernet IPv4 address. Edit root `.env` to bind the API to `0.0.0.0`, then run `docker compose up -d --wait` from the root. Allow the API port (8000 by default) and Expo's Metro port (8081 by default) through Windows Firewall on your trusted private network. The phone and PC must be able to reach each other; guest Wi-Fi isolation or a VPN may prevent this. A phone's `localhost` points to the phone, not the PC. Never use the Compose hostname `db` in the mobile URL.

If you change `API_PORT`, update the mobile URL too. After changing the mobile environment, fully reload the app; restarting with `npx.cmd expo start --clear` also clears Metro's cache. An Expo tunnel exposes Metro, not this backend. These HTTP URLs are for local Expo Go development; standalone release builds need a separately configured HTTPS backend.

The mobile app uses Expo Router and offers registration/login, the book-value dashboard, reserve settings, ledger entry, external-trade recording, FIFO holdings/lots, hypothetical analysis, decision list/detail/review, private book-library, and Karachi property-research screens. The original thesis and financial outcome are displayed separately, and all investment and opportunity screens state that the app places no orders. The access token is encrypted with Expo SecureStore. Native behavior still needs an emulator or physical-phone smoke test.

## Checks

## Extensible opportunity analysis and Karachi property research

The authenticated opportunity API uses a domain/analyzer registry and a source-adapter boundary so later research domains can be added without mixing their records or rules into the finance ledger. Part 8 registers only `karachi_real_estate`, with manual or authorized-export listing entry. A supplied Zameen or other HTTP(S) URL is normalized and stored as provenance; the service does not fetch or crawl it.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/opportunities/domains` | List registered research domains |
| `POST`, `GET` | `/opportunities/karachi-real-estate/listings` | Record or filter user-owned Karachi listing research |
| `POST` | `/opportunities/analyze/karachi_real_estate/comparables` | Calculate asking-price range and median when at least three records match |
| `POST` | `/opportunities/analyze/karachi_real_estate/yield` | Calculate gross yield and, when all costs are supplied, net yield |

Listing writes and analysis writes require `Idempotency-Key`. Records preserve source name/reference, observation time, normalized input, evidence listing IDs and dates, assumptions, exact Decimal metrics, analyzer version, and limitations. Asking prices are labeled unverified and never treated as completed transactions. Records older than 90 days are labeled stale. Area units must be explicit: `sq_ft`, `sq_yd`, one of the two named marla definitions, or one of the two named kanal definitions.

Gross annual yield is `(monthly rent × 12) / purchase price × 100`. Net yield is unavailable until the user supplies both annual expense assumptions and an annual property-tax assumption; the app supplies no tax rate, legal conclusion, vacancy rate, or transaction cost. Results are estimates with no recommendation, offer, order, or broker action.

Property research does not change ledger cash, investment book value, emergency reserves, or investable cash. The dashboard retains ledger-only `net_worth_book_value` and separately reports `confirmed_property_value` and `net_worth_with_confirmed_property`. A property value is included there only when the listing is marked user-owned and has an explicitly confirmed valuation and confirmation timestamp.

Apply and verify the migration in PowerShell:

```powershell
docker compose run --rm api alembic upgrade head
docker compose exec api alembic current
docker compose exec api alembic check
```

## Marketplace product research and resale outcomes

The `marketplace_resale` domain accepts user-entered data, authorized exports, or documented permitted API data. Supported platform labels are Daraz, Temu, SHEIN, and Other. URLs are stored for provenance and deduplication and are never fetched. Source observations remain separate from local selling assumptions, estimates, and actual outside-app outcomes.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/marketplace/listings` | Record or list product-source observations |
| `POST` | `/opportunities/analyze/marketplace_resale/margin` | Store an immutable cost and margin estimate |
| `GET` | `/marketplace/analyses` | List saved estimates for outcome selection |
| `POST`, `GET` | `/marketplace/outcomes` | Record or list outside-app purchases and sales |

Writes require `Idempotency-Key`. Observations over 60 days old are stale. Cross-currency calculations require a dated rate and source. Every cost category must be supplied explicitly, including zero when it does not apply. Missing required inputs make the metrics unavailable.

- `landed cost = source price × exchange rate + shipping + customs + conversion fee`
- `break-even = landed cost + selling/payment fees + packaging + delivery + other costs + returns/damage/unsold allowances`
- `gross margin = expected selling price - landed cost`
- `net margin = expected selling price - break-even`
- `net margin % = net margin / expected selling price × 100`
- `inventory cash ROI = net margin / break-even × 100`

Outcomes retain the original estimate and report actual net result, forecast error, and assumption differences without assigning a success label. Inventory does not change ledger cash, investments, reserves, or investable cash. Confirmed inventory valuation appears only in separate dashboard fields; cash movement requires a separate balanced finance entry. The app provides no demand rank, rates, predictions, purchasing, listing, advertising, fulfilment, or payment execution.

## Personal financial book library

## Karachi marketplace intelligence

Part 10 adds a normalized, historical intelligence layer at `/api/v1/marketplace`. The sole active market is Pakistan / Sindh / Karachi / PKR (`Asia/Karachi`). Products remain user owned. Observations, Karachi sourcing options, competition signals, rankings, and watchlists preserve source classification, reference, observation date, and evidence. No URL is fetched by the server.

Deterministic matching normalizes case, whitespace, punctuation, common unit spacing, brand, model text, and saved aliases. It returns `exact_match`, `probable_match`, `ambiguous`, or `unmatched`. CSV/JSON imports always pass through parse, validation, mapping, preview, duplicate review, explicit row actions, and atomic commit. Imported rankings and margins are ignored; the application recalculates them from accepted evidence. Explicit merge and split operations retain aliases, move selected evidence, archive merged sources, and create audit events. Observations and ranking snapshots remain historical.

Freshness policy is centralized: marketplace price and competition evidence are fresh through 7 days and aging through 14; demand and sourcing evidence are fresh through 14 days and aging through 28. Older records are stale. Research readiness reports identity completeness, recent price, sourcing, competition, demand, margin, unresolved matches, stale evidence, warnings, and missing fields. File size, row count, and batch-ranking limits use `MARKETPLACE_IMPORT_MAX_BYTES`, `MARKETPLACE_IMPORT_MAX_ROWS`, and `MARKETPLACE_BATCH_RANK_MAX`.

Research Score weights are demand 25%, margin 25%, competition 15%, sourcing 15%, logistics 10%, and evidence confidence 10%. Margin reads the saved Part 9 calculation. Missing components remain unavailable, are listed in the explanation, and reduce confidence. Each snapshot includes component reasons, weights, missing inputs, and limitations. A Research Score is not a success prediction or guarantee.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/marketplace/market` | Read the active Karachi market context |
| `POST`, `GET` | `/api/v1/marketplace/products` | Create normalized products or filter/sort research |
| `GET` | `/api/v1/marketplace/products/{id}` | Read full product intelligence |
| `POST`, `GET` | `/api/v1/marketplace/products/{id}/observations` | Append/view marketplace and demand history |
| `POST`, `GET` | `/api/v1/marketplace/products/{id}/sourcing` | Add/view Karachi sourcing evidence |
| `POST`, `GET` | `/api/v1/marketplace/products/{id}/competition` | Add/view competition evidence |
| `POST` | `/api/v1/marketplace/products/{id}/rank` | Store an explainable ranking snapshot |
| `GET` | `/api/v1/marketplace/rankings` | Review ranking history |
| `POST` | `/api/v1/marketplace/compare` | Compare two to four products |
| `GET`, `POST` | `/api/v1/marketplace/watchlist` | List/add watchlist entries |
| `PUT`, `DELETE` | `/api/v1/marketplace/watchlist/{id}` | Update/remove an owned entry |
| `POST`, `GET` | `/api/v1/marketplace/imports` | Upload CSV/JSON evidence or list import batches |
| `GET` | `/api/v1/marketplace/imports/{id}/preview` | Review normalized rows, validation, and proposed matches |
| `POST` | `/api/v1/marketplace/imports/{id}/mapping` | Replace the column mapping and revalidate |
| `PUT` | `/api/v1/marketplace/imports/{id}/rows/{row_id}` | Choose create, attach, skip, or review for a row |
| `POST` | `/api/v1/marketplace/imports/{id}/commit` | Commit every resolved row atomically |
| `POST` | `/api/v1/marketplace/products/merge` | Merge two owned products and preserve an audit snapshot |
| `POST` | `/api/v1/marketplace/products/{id}/split` | Split selected evidence into a new owned product |
| `GET` | `/api/v1/marketplace/products/{id}/history` | Read chronological identity, evidence, merge/split, ranking, and watchlist events |
| `GET` | `/api/v1/marketplace/products/{id}/data-quality` | Read freshness, completeness, warnings, and research readiness |
| `GET`, `POST` | `/api/v1/marketplace/research-presets` | List/create saved filter and sorting presets |
| `PUT`, `DELETE` | `/api/v1/marketplace/research-presets/{id}` | Update/delete an owned preset |
| `POST` | `/api/v1/marketplace/research-presets/{id}/run` | Run a validated preset |
| `POST` | `/api/v1/marketplace/rankings/batch` | Recalculate bounded product batches with per-item results |
| `GET` | `/api/v1/marketplace/exports/{kind}?format=csv|json` | Export owned products, rankings, watchlist, or observations |

Authenticated users can upload owned or authorized `.txt`, `.epub`, and text-based `.pdf` files through `POST /books`. Files are stored under UUID keys in the private Docker `book_data` volume and are never served by public URLs. The default limit is 20 MiB (`BOOK_MAX_UPLOAD_BYTES`). Metadata can be listed, viewed, patched, reprocessed, or deleted with `/books` routes; deletion removes database passages and the private source file.

Extraction preserves TXT section, EPUB chapter-file, and PDF page references. Image-only PDFs are marked `ocr_required`; OCR is not implemented. Source SHA-256 and extraction version prevent duplicate passages during unchanged reprocessing. `GET /book-search?q=...` uses an indexed PostgreSQL full-text vector and returns short cited excerpts. No LLM, embedding service, generated answer, unauthorized downloader, market-data inference, or buy/sell instruction is included.

`POST /decisions/{decision_id}/passages/{passage_id}` attaches an owned citation as learning support. The audit event explicitly records that the link does not affect decision scoring, transaction outcomes, tax calculations, risk checks, or order execution. Back up both PostgreSQL and the `book_data` volume together; database-only backups do not contain source files.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/books` | Upload/process or list private books |
| `GET`, `PATCH`, `DELETE` | `/books/{id}` | View/update metadata or delete book and passages |
| `POST` | `/books/{id}/reprocess` | Traceably re-run extraction without duplicates |
| `GET` | `/book-search` | Search owned passages with citations |
| `GET` | `/book-passages/{id}` | Open an owned cited result |


From the repository root:

```powershell
docker compose config --quiet
docker compose up --build -d --wait
docker compose --profile test run --build --rm test
docker compose --profile test stop test-db
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
Invoke-RestMethod http://localhost:8000/health/ready
```

Backend tests cover all earlier behavior plus decision ownership/linking, immutable rationale, append-only reviews and audits, realized/open/unavailable outcomes, fee/tax breakdowns, tax-rule version use, process/outcome separation, scoped exports, and absence of broker-order routes. Tests mutate only the isolated temporary test database.

```powershell
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo install --check
npx.cmd expo-doctor
```

## Cited read-only research assistant

Part 12 adds authenticated conversations under `/assistant`. The assistant searches only the authenticated user's stored records. It uses PostgreSQL full-text search for book passages and structured, user-scoped queries for ledger totals, holdings, saved sale analyses, tax assumptions, decision/review records, property evidence and calculations, and marketplace observations and ranking snapshots. It references existing deterministic outputs and does not recalculate gains, fees, taxes, yields, margins, or scores in generated text.

The default `ASSISTANT_PROVIDER=disabled` mode performs no model or network call. It returns a deterministic evidence summary with numbered citations, calculation references, freshness labels, limitations, and an explicit insufficient-evidence response. Book passages, imported files, and listing text are untrusted evidence; instructions contained in them are never treated as assistant instructions.

`ASSISTANT_PROVIDER=openai_compatible` is optional. It requires `ASSISTANT_PROVIDER_URL`, `ASSISTANT_PROVIDER_MODEL`, and `ASSISTANT_PROVIDER_API_KEY`. When enabled, the user's question and the bounded retrieved excerpts leave this application and are sent to that provider. Review the provider's privacy, retention, residency, and billing terms first. API keys belong only in the server environment and must never use an `EXPO_PUBLIC_*` variable. Provider failure or missing citation markers falls back to deterministic mode. Generated wording is not independently verified, and citations do not establish suitability.

### Optional local OpenAI-compatible provider

Part 14 adds `ASSISTANT_PROVIDER=local_openai_compatible`. It is disabled by default, requires no paid API, and accepts only `localhost`, loopback addresses, or Docker's `host.docker.internal` gateway. Redirects and environment HTTP proxies are disabled for local-provider calls so evidence cannot be redirected or forwarded elsewhere by this adapter. The API never installs Ollama, downloads a model, browses the network for the model, or gives the model database, shell, browsing, or write tools.

Ollama is one compatible option. Install and run it separately. On Windows, its API normally uses port 11434. Select and download a model explicitly; model names, licenses, disk use, RAM/VRAM needs, speed, and quality vary:

```powershell
# Run these outside this repository after installing Ollama.
# These user variables take effect after Ollama is restarted.
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')

# Explicit operator action: this downloads the chosen model. The API never runs it.
ollama pull <model-name>
ollama list
```

Keep Windows Firewall access limited to the local machine/trusted private network. Then set these values in the root `.env` and rebuild the API:

```dotenv
ASSISTANT_PROVIDER=local_openai_compatible
ASSISTANT_LOCAL_PROVIDER_URL=http://host.docker.internal:11434/v1
ASSISTANT_LOCAL_PROVIDER_MODEL=<model-name>
ASSISTANT_PROVIDER_TIMEOUT_SECONDS=15
ASSISTANT_PROVIDER_MAX_CONCURRENCY=2
ASSISTANT_PROVIDER_MAX_REQUEST_BYTES=65536
ASSISTANT_PROVIDER_MAX_RESPONSE_BYTES=32768
```

```powershell
docker compose up --build -d --wait
docker compose logs --tail 100 api
```

The application supplies only the bounded authorized evidence bundle and deterministic draft. It rejects changed numbers, changed citation markers, fabricated citation objects, malformed/oversized output, redirects, timeouts, and connection errors, then returns deterministic mode. Request limits may need to be reduced on machines with limited memory. Ollama notes that model storage can require tens to hundreds of GB and that parallel/context settings increase memory demand. CPU-only inference can be slow. A passing test suite does not establish model quality or financial, tax, or legal suitability. See the [Ollama Windows guide](https://docs.ollama.com/windows) and [Ollama FAQ](https://docs.ollama.com/faq).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/assistant/conversations` | Create or list the user's bounded conversation history |
| `GET`, `DELETE` | `/assistant/conversations/{id}` | Read or permanently delete one owned conversation and its messages |
| `POST` | `/assistant/conversations/{id}/messages` | Retrieve owned evidence and return a cited read-only answer |
| `POST` | `/assistant/messages/{id}/feedback` | Record a privacy-minimized quality report; creates no financial action |
| `GET` | `/assistant/feedback` | List the authenticated user's private feedback inbox |
| `PUT`, `DELETE` | `/assistant/feedback/{id}` | Review/update or delete one owned report |
| `POST` | `/assistant/feedback/export` | Export explicitly selected reviewed reports as sanitized fixture candidates |
| `GET` | `/assistant/metrics` | Return the user's aggregate request, fallback, citation, and latency metrics |

Questions are limited to 4,000 characters. Defaults allow 20 conversations, 50 messages per conversation, 8 retrieved records, and 12,000 evidence characters. Configure these with `ASSISTANT_MAX_CONVERSATIONS`, `ASSISTANT_MAX_MESSAGES_PER_CONVERSATION`, `ASSISTANT_RETRIEVAL_LIMIT`, and `ASSISTANT_MAX_CONTEXT_CHARS`. Only assistant conversation/message records are created or deleted; no financial or research record is mutated.

## Assistant evaluation and reliability

Part 13 validates every provider response against the bounded response schema and the exact user-authorized retrieval set before it is returned. Fabricated or altered citations, calculation references that differ from stored deterministic outputs, malformed provider data, missing citation markers, and oversized output trigger a deterministic fallback. Freshness labels are derived from stored source metadata. External wording cannot replace the existing calculation services.

Privacy-minimized `assistant_request` audit events contain only outcome, provider/response mode, latency, citation count, and validation/fallback state. They do not contain prompts, answers, passages, tokens, secrets, or financial values. Feedback stores only the selected quality category and message identity. Metrics and feedback remain user scoped; deleting a conversation deletes its message content, while minimal audit records remain for operational history.

The versioned synthetic dataset and offline runner need neither a provider nor network access:

```powershell
docker compose --profile test run --build --rm `
  -v "${PWD}\docs\evaluations:/reports" test `
  python -m evaluation.runner `
  --json /reports/part-13-evaluation.json `
  --markdown /reports/part-13-evaluation.md
```

Checked-in results are in [JSON](docs/evaluations/part-13-evaluation.json) and [Markdown](docs/evaluations/part-13-evaluation.md). The evaluation measures citations, ownership, abstention, stale/conflicting evidence labels, exact deterministic calculation agreement, read-only state boundaries, cross-user isolation, and prompt-injection handling. Passing is a regression signal; it does not prove advice suitability, universal correctness, or regulatory compliance. Part 13 needs no schema change, so Alembic remains at `20261001_0011`.

## Supervised response feedback

Part 15 extends the existing Part 13 feedback endpoint. Each owned assistant response can have one report in a fixed category: `helpful`, `inaccurate`, `unsupported`, `stale`, `confusing`, or `missing_evidence`. An optional user note is limited to 500 characters. A duplicate submission returns HTTP 409; use the report's update endpoint to change its category, note, personal review annotation, or status.

The application has no administrator or reviewer role. `/assistant/feedback` is therefore a private personal review inbox with `submitted`, `reviewed`, and `dismissed` states. It retains response mode, citation record IDs, source dates, freshness labels, calculation-service names, and validation/fallback metadata. It does not duplicate prompts, answers, citation excerpts, financial values, or provider secrets. Deleting feedback deletes its feedback event only; it does not delete or change the assistant conversation or any financial/research record.

A report must be marked `reviewed`, explicitly selected for fixture export, included by ID in the export request, and confirmed with `confirm_sanitized_export: true`. The exported `assistant-feedback-regression-v1` document strips user/message/record IDs, prompts, answers, account data, balances, raw passages, user notes, annotations, and secrets. Export creates a candidate for manual regression-test implementation; it does not modify the checked-in evaluation dataset, train a model, fine-tune anything, alter prompts, or change provider settings.

## Remaining work

See the [Part 1](docs/part-1-report.md), [Part 2](docs/part-2-report.md), [Part 3](docs/part-3-report.md), [Part 4](docs/part-4-report.md), [Part 5](docs/part-5-report.md), [Part 6](docs/part-6-report.md), [Part 7](docs/part-7-report.md), [Part 8](docs/part-8-report.md), [Part 9](docs/part-9-report.md), [Part 10](docs/part-10-report.md), [Part 11](docs/part-11-report.md), [Part 12](docs/part-12-report.md), [Part 13](docs/part-13-report.md), [Part 14](docs/part-14-report.md), and [Part 15](docs/part-15-report.md) verification reports.

## Opt-in multi-device notifications

Part 16 adds informational notifications through a transactional PostgreSQL outbox and a separate `notification-worker` Compose service. Every preference defaults off. A device must register a valid Expo token, enable notifications, and opt in both at user and device level before it is eligible for fanout.

Supported event types are limited to `reminder_due`, explicitly requested `assistant_response_ready`, and `feedback_review_status_changed`. Push payloads contain fixed generic text, an event ID/type, and an allowlisted in-app path. They never contain balances, holdings, tax data, book passages, marketplace/property content, prompts, assistant answers, or transaction instructions.

Part 17 adds `GET /notifications/diagnostics` and `POST /notifications/test`. Diagnostics expose registration, permission-independent server state, opt-in eligibility, last delivery/receipt state, and sanitized error codes without exposing tokens. Test sends require selected owned active devices, `confirm_send: true`, and an idempotency key; they are rate limited and use the normal outbox. See [the two-device test guide](docs/part-17-device-test.md) and [Part 17 report](docs/part-17-report.md).

## PSX historical research

Part 18 provides an authenticated, user-scoped workspace under `/api/v1/psx`. It accepts manually supplied or otherwise authorized CSV files, previews every row, requires explicit resolution of duplicates and invalid rows, and commits reviewed rows atomically. It does not scrape, poll, call a broker, download missing prices, send price alerts, or create trades.

CSV columns are `symbol,observation_date,open,high,low,close,volume,currency,source,adjustment_type`. Dates use `YYYY-MM-DD`; prices are positive decimals with at most four places; volume is a nonnegative whole number; currency is `PKR`; adjustment type is `raw` or `adjusted`. High must be at least open, low, and close; low must be at most them. Source/provenance is required. Uploaded evidence is labeled unverified.

- `POST/GET /api/v1/psx/imports`
- `GET /api/v1/psx/imports/{id}/preview`
- `PUT /api/v1/psx/imports/{id}/rows/{row_id}`
- `POST /api/v1/psx/imports/{id}/commit` or `/cancel`
- `GET /api/v1/psx/instruments` and `/instruments/{symbol}/history`
- `POST /api/v1/psx/analysis`

Analysis returns period return, annualized rolling volatility, moving average, and RSI when enough observations exist. Results include observation IDs, source dates, sources, raw/adjusted status, freshness, detected gaps, formulas, and limitations. An `as_of_date` excludes later observations to prevent look-ahead. Results are hypothetical historical evidence without buy/sell/suitability labels. See [Part 18 report](docs/part-18-report.md).

For production set a unique `AUTH_SECRET`, `APP_ENV=production`, `APP_DEBUG=false`, explicit `ALLOWED_HOSTS`, HTTPS-only `ALLOWED_ORIGINS` when browser origins are needed, and `REQUIRE_HTTPS=true`. Startup fails closed when these controls are insecure. Terminate TLS at a trusted proxy and keep PostgreSQL, the API, and worker on a private network.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST`, `GET` | `/notifications/devices` | Register/rotate the current token or list owned devices |
| `PUT`, `DELETE` | `/notifications/devices/{id}` | Enable/disable or revoke a device and device-bound session |
| `GET`, `PUT` | `/notifications/preferences` | Read/update user or per-device event opt-ins |
| `POST` | `/notifications/reminders` | Idempotently enqueue an informational reminder |
| `GET` | `/notifications/history` | View per-device delivery and dead-letter states |
| `POST` | `/notifications/history/{id}/acknowledge` | Mark an owned in-app history item acknowledged |

The outbox uniquely identifies each event and device delivery. The worker sends only after the creating database transaction commits. It records pending, retry, accepted, delivered-to-provider, permanent-failure, dead-letter, and unknown states; retries transient failures at most four times with exponential backoff; polls Expo receipts after 15 minutes; and deactivates `DeviceNotRegistered` tokens. Expo ticket acceptance means Expo accepted the request, and a successful receipt means APNs/FCM accepted it. Neither state proves the phone displayed the notification.

Mobile login/register requests include a locally generated installation ID so that device revocation invalidates that device-bound JWT. Logout attempts server revocation before removing the encrypted local access token. Older API clients that omit device metadata continue to receive ordinary short-lived user tokens.

Remote push requires a physical device and an Expo development/production build; Expo Go does not support remote push for this SDK. Configure `EXPO_PUBLIC_EAS_PROJECT_ID` in `mobile/.env`, set up Android FCM v1 and/or Apple push credentials through EAS, then use the Notifications screen to request permission and register. The optional server-side `EXPO_ACCESS_TOKEN` supports Expo enhanced push security and must remain only in the root `.env`.

Worker operations:

```powershell
docker compose up --build -d --wait
docker compose logs --follow --tail 100 notification-worker
# One-off recovery/diagnostic passes:
docker compose exec notification-worker python -m app.notification_worker send
docker compose exec notification-worker python -m app.notification_worker receipts
```

Part 16 is complete. Notifications remain informational and cannot place orders, make offers or purchases, mutate financial records, or turn assistant output into executable instructions. Market polling, price alerts, inferred urgency, and external market-data collection are not implemented.

Assistant chat remains available from the main mobile screen on iOS and Android. Each request has an explicit, off-by-default **Notify me when ready** choice. An assistant-ready push contains only generic text, event metadata, an allowlisted `/assistant` route, and the opaque conversation UUID. After authentication, tapping it opens that owned conversation; the push never includes the question, answer, citations, evidence, limitations, or financial data.

References: [Compose startup and health checks](https://docs.docker.com/compose/how-tos/startup-order/), [Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/), and [Expo environment variables](https://docs.expo.dev/guides/environment-variables/).
