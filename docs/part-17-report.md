# Part 17 report

Part 17 adds safe device diagnostics, explicit generic test notifications, authenticated deep-link checks, production configuration validation, and a repeatable two-phone runbook. The test event uses the existing transactional outbox and worker. It requires selected owned active devices, literal confirmation, an idempotency key, and is limited to three new test events per user per ten minutes.

Migration `20261002_0013` extends only the notification event allowlist with `test_notification`; existing preference defaults remain conservative. No development data or volume is reset.

Production startup now rejects debug mode, wildcard/missing hosts, non-HTTPS origins, disabled HTTPS enforcement, known local secrets, and invalid token lifetimes. Deploy behind a TLS-aware proxy and configure `ALLOWED_HOSTS`, optional HTTPS `ALLOWED_ORIGINS`, and `REQUIRE_HTTPS=true`.

Back up PostgreSQL with `docker compose exec -T db pg_dump -U wealth_local -d wealth_manager -Fc > backups\wealth-manager.dump`. Back up private books separately from the named `book_data` volume. Test restoration into a separate empty database before any incident. Stop API and worker writes, verify the target and backup, restore with `pg_restore`, run `alembic current`, compare row counts and checksums, and restart services only after validation. Never test restore by overwriting the live volume.

Automated coverage includes authorization, diagnostics redaction, explicit confirmation, selected-device fanout, idempotency, rate limiting, inactive/cross-user rejection, payload privacy, worker retry/receipt behavior, and deep-link allowlisting. Physical-device delivery remains unverified; use [the device test guide](part-17-device-test.md).

## Verification

- Full Docker backend suite from a clean disposable database: **110 passed**, one upstream Starlette/httpx deprecation warning, 25.63 seconds.
- Part 13 offline evaluation: **14/14 passed**, provider disabled and network unavailable.
- Mobile TypeScript and Expo lint: passed. Mocked notification navigation: **5/5 passed**.
- Expo dependency check: dependencies current. Expo Doctor: **21/21 checks passed**.
- Alembic: `20261002_0013 (head)`; `alembic check` reported no new upgrade operations.
- Compose configuration: valid. Development API, PostgreSQL, and notification worker: healthy. `/health/live` returned `ok`; `/health/ready` returned database `connected`.
- PostgreSQL system identifier before and after: `7690665958609113124`. Development user count before and after: `0`. The named development volume was not removed or recreated.
- Real iOS/Android devices: **not tested**. No claim of actual push display, foreground/background/terminated behavior, or two-phone delivery is made.

Files changed include the notification model/service/routes/schemas, migration and tests; production config/middleware, Compose and environment example; mobile settings/types/deep-link tests; README; this report and the device test guide. Known limits are Expo/platform credential dependence, provider acceptance not proving display, device diagnostics knowing only the current phone's OS permission, and manual backup/restore validation.
