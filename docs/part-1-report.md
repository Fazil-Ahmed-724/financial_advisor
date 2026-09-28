# Part 1 implementation and verification

Verified September 29, 2026 (Asia/Karachi).

## Starting state

The workspace contained only `.git`. `git status --branch --short` reported no commits, and `git ls-tree HEAD` could not find a HEAD commit. No backend, Docker Compose configuration, mobile app, tests, README, schema, or pre-existing source files were present.

Tools available: Docker 29.5.3, Compose v5.1.4, Node 24.15.0, and Python 3.14.5. Host Python was not used to run the backend; Docker uses Python 3.13. PowerShell blocked the npm `.ps1` wrapper, so all npm/Expo commands used `.cmd` wrappers. Sandbox access initially blocked Docker and npm network access; authorized retries succeeded.

## Changed files

All deliverable files are new and remain uncommitted.

| Files | Purpose |
| --- | --- |
| `compose.yaml` | API and PostgreSQL services, health checks, persistent volume, optional test service |
| `.env.example`, `.gitignore` | Local settings and secret/build-output exclusions |
| `backend/Dockerfile`, `backend/.dockerignore` | Non-root runtime image and separate test target |
| `backend/requirements.txt`, `backend/requirements-dev.txt` | Pinned direct runtime/test dependencies |
| `backend/app/__init__.py`, `backend/app/database.py`, `backend/app/main.py` | Package, environment-based PostgreSQL check, liveness/readiness endpoints |
| `backend/tests/test_health.py` | Three health and connectivity tests |
| `mobile/App.tsx`, `mobile/index.ts` | Mobile connection-check screen and Expo entry point |
| `mobile/app.json`, `mobile/tsconfig.json`, `mobile/eslint.config.js` | Expo, TypeScript, and lint configuration |
| `mobile/package.json`, `mobile/package-lock.json` | SDK 57 dependencies and reproducible npm installation |
| `mobile/.env.example`, `mobile/.gitignore` | Public API URL example and generated-file exclusions |
| `mobile/AGENTS.md`, `mobile/CLAUDE.md`, `mobile/.claude/settings.json`, `mobile/LICENSE` | Files included by the official Expo template |
| `mobile/assets/icon.png`, `mobile/assets/favicon.png`, `mobile/assets/splash-icon.png`, `mobile/assets/android-icon-background.png`, `mobile/assets/android-icon-foreground.png`, `mobile/assets/android-icon-monochrome.png` | Official starter image assets |
| `README.md`, `docs/part-1-report.md` | PowerShell setup, networking, scope, and verification record |

Local `.env` and `mobile/.env` copies and `mobile/node_modules` were also created and are ignored by Git. No credentials were added to source files; only explicitly public example values are in `.env.example`.

## Commands and results

Commands below ran from the root unless identified as mobile commands. Inspection also used `rg --files`, `Get-ChildItem`, `Get-Content`, `git status`, `git log`, and tool version checks.

| Command | Result |
| --- | --- |
| `npx.cmd --yes create-expo-app@latest mobile --template blank-typescript --no-install` | Official Expo starter created |
| `Copy-Item .env.example .env` | Local backend environment created |
| `Copy-Item mobile/.env.example mobile/.env` | Local emulator URL configured |
| `docker compose config --quiet` | Passed |
| `docker compose up --build -d --wait` | Built API, initialized new PostgreSQL volume, both services healthy |
| `docker compose --profile test run --build --rm test` | 3 tests passed; 1 upstream deprecation warning |
| `docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"` | PostgreSQL connection OK |
| `Invoke-RestMethod http://localhost:8000/health/ready` | `status=ok`, `database=connected` |
| `docker compose ps` | API and database healthy; API bound to `127.0.0.1:8000`; database not published |
| `docker compose logs --tail 10 api db` | API HTTP 200 responses and database ready |
| `docker compose exec db pg_controldata /var/lib/postgresql/data` | Recorded cluster identifier before recreation |
| `docker compose down`, then `docker compose up -d --wait` | Container recreation succeeded, without deleting volume |
| `docker compose exec db pg_controldata /var/lib/postgresql/data` (filtered to identifier) | Same cluster identifier before and after: `7690665958609113124` |
| Readiness request after recreation | Still connected |
| `npm.cmd install` (mobile) | Dependencies installed; lockfile generated |
| `npx.cmd expo install eslint eslint-config-expo --dev` (mobile) | Expo-compatible lint dependencies installed |
| `npm.cmd run typecheck` (mobile) | Passed |
| `npm.cmd run lint` (mobile) | Generated standard ESLint config and passed |
| `npx.cmd expo install --check` (mobile) | Dependencies up to date |
| `npx.cmd expo-doctor` (mobile) | 21/21 checks passed |
| `npm.cmd audit --json` (mobile) | Exit 1: 10 moderate advisories; no high or critical advisories |
| `git check-ignore .env mobile/.env` | Both local environment files ignored |

## Limitations and remaining work

- The containers are left running and healthy at `http://localhost:8000`. Expo Metro was not left running.
- Native emulator/physical-phone execution was not performed. TypeScript/lint/Doctor checks do not substitute for tapping the connection-check button on a real device.
- npm's 10 moderate findings trace through Expo tooling to `xcode` / `uuid`. The audit-proposed top-level fix is a breaking downgrade to Expo 46.0.21. No forced downgrade or unverified dependency override was applied; revisit with an SDK-compatible upstream fix before release.
- The backend test suite emitted a Starlette warning that its `httpx` TestClient integration is deprecated in favor of `httpx2`; all tests passed. npm also reported upstream `uuid` and ESLint deprecation notices.
- Direct Python dependencies are pinned; transitive Python dependencies and Docker image tags are not fully locked by hashes/digests.
- Part 2 has not started. There are no migrations, application tables, authentication, finance features, book ingestion, market data, or recommendations. Device notifications and release credentials remain later-phase work.
