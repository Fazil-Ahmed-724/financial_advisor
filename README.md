# Personal AI Wealth Manager

Phase 1, Parts 1–3: Dockerized FastAPI and PostgreSQL, Alembic migrations, authentication, user-owned PKR accounts, a balanced journal, and an Expo mobile client.

## Initial inspection

The supplied repository contained only `.git`, with no commits or tracked files. Part 1 created the Docker/backend/mobile foundation, Part 2 added authentication, and Part 3 adds accounts and deterministic double-entry records. Stock trades, market values, books, recommendations, notifications, and broker integrations are not implemented. Tables are created only by Alembic migrations; application code never calls `Base.metadata.create_all()`.

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

Review every generated migration before applying it. `downgrade` can destroy data and is intentionally omitted from the normal development workflow. Revision `20260929_0001` creates users. Revision `20260929_0002` creates accounts, journal entries/lines, idempotency records, ownership constraints, and deferred balance checks.

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

The mobile app uses Expo Router and offers registration/login, account creation, opening/income/expense entry screens, server-fetched account choices, and refreshed balances. The access token is encrypted with Expo SecureStore and restricted to the current device where supported. Native device behavior still needs a manual emulator/phone smoke test. Web development is not configured because SecureStore targets Android and iOS.

## Checks

From the repository root:

```powershell
docker compose config --quiet
docker compose up --build -d --wait
docker compose --profile test run --build --rm test
docker compose --profile test stop test-db
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
Invoke-RestMethod http://localhost:8000/health/ready
```

Backend tests cover clean migration history, schema/model consistency, authentication, all account types, normalization, balanced entries, invalid amounts and precision, ownership isolation, idempotent replay/conflicts, balance calculations, API rollback, database-trigger rollback, health checks, and safe errors. Tests mutate only the isolated temporary test database.

```powershell
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo install --check
npx.cmd expo-doctor
```

## Remaining work

See the [Part 1](docs/part-1-report.md), [Part 2](docs/part-2-report.md), and [Part 3](docs/part-3-report.md) verification reports.

Part 3 is complete. Parts 4–8 cover reserves/dashboard, FIFO investment records, multi-device alerts, authorized book library, and integration/release checks. Expo push credentials, notification testing on real phones, user-provided book files, and OCR decisions belong to those later parts.

References: [Compose startup and health checks](https://docs.docker.com/compose/how-tos/startup-order/), [Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/), and [Expo environment variables](https://docs.expo.dev/guides/environment-variables/).
