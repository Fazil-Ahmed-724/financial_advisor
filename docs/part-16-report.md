# Part 16 implementation and verification

Verified October 2, 2026 (Asia/Karachi).

Part 16 adds opt-in, user-scoped multi-device informational notifications. The repository had no prior device, outbox, receipt, preference, or Expo push implementation, so migration `20261002_0012` adds the required schema after the Part 15 baseline. It was applied in place; the development PostgreSQL volume and existing data were preserved.

## Architecture and guarantees

The migration adds `notification_devices`, `notification_preferences`, `device_notification_preferences`, `notification_events`, and `notification_deliveries`. Event creation and eligible-device fanout occur in the same database transaction. A unique user/event/dedupe key prevents duplicate logical events, while a unique event/device constraint prevents duplicate delivery records.

The separate `notification-worker` Compose service claims committed pending work with `FOR UPDATE SKIP LOCKED`; API requests never call Expo. The worker records `pending`, `retry`, `accepted`, `delivered`, `permanent_failure`, `dead_letter`, and `unknown` states. Transient request failures and rate-limit receipt errors use bounded exponential backoff with four total attempts. Ticket and receipt errors classify invalid tokens, permanent payload/credential failures, transient failures, timeouts, and missing/unknown receipts. `DeviceNotRegistered` clears the token and disables the device. Worker restart recovery follows from persisted status, attempt count, and `next_attempt_at`.

Receipts are scheduled 15 minutes after ticket acceptance, consistent with Expo guidance. `accepted` means Expo accepted the push request; `delivered` means APNs/FCM accepted it according to the Expo receipt. Neither proves that a device displayed the notification.

All user and device event preferences default off. Eligibility requires an active token, device enabled, user event enabled, and device event enabled. The allowlist is `reminder_due`, explicitly requested `assistant_response_ready`, and `feedback_review_status_changed`. Assistant tools and initial feedback submissions cannot create notification events. Notification actions are informational and expose no financial mutation capability.

Provider payloads use fixed generic title/body text plus a notification ID, allowlisted event type, and allowlisted authenticated-app path. An assistant-ready payload also carries the opaque owned conversation UUID so the authenticated app can open the relevant conversation. It contains no question, answer, citation, balance, holding, tax value, passage, property/marketplace content, or transaction instruction. Tokens and message content are not logged.

## Device sessions and mobile behavior

Mobile authentication now supplies a locally stored installation UUID, platform, and display name. The backend issues a JWT containing the device ID and session version. Revoking that owned device clears its token, disables pending delivery, increments its session version, and immediately invalidates that device-bound JWT. Older clients may omit device metadata and retain the existing short-lived user-token behavior.

The Expo SDK 57 app uses `expo-notifications` and `expo-device`. Registration is explicit, requests permission only from the settings screen, handles denial or token failure visibly, and initially leaves delivery disabled. Registering again safely rotates the token. Logout attempts device revocation before deleting the SecureStore token; local logout still completes during an API outage. Notification taps validate authentication, event type, allowlisted path, and UUID shape. Assistant-ready taps open the referenced conversation through its existing user-scoped API; malformed, unauthenticated, or unsupported routes are ignored.

Remote push requires a physical device and development/production build; it is unavailable in Expo Go for this SDK. `EXPO_PUBLIC_EAS_PROJECT_ID`, Android FCM v1 credentials and/or Apple push credentials remain operator requirements. No real push or physical-device test was performed.

## API

- `POST`, `GET /notifications/devices`
- `PUT`, `DELETE /notifications/devices/{device_id}`
- `GET`, `PUT /notifications/preferences`
- `POST /notifications/reminders`
- `GET /notifications/history`
- `POST /notifications/history/{delivery_id}/acknowledge`

Assistant message requests additionally accept `notify_when_ready: true`; it still requires both preference levels and eligible devices before any delivery record is created.

## Changed files

- `.env.example`
- `compose.yaml`
- `README.md`
- `backend/alembic/versions/20261002_0012_notifications.py`
- `backend/app/auth.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/notification_provider.py`
- `backend/app/notification_service.py`
- `backend/app/notification_worker.py`
- `backend/app/routes_assistant.py`
- `backend/app/routes_auth.py`
- `backend/app/routes_notifications.py`
- `backend/app/schemas.py`
- `backend/app/schemas_assistant.py`
- `backend/app/schemas_notifications.py`
- `backend/tests/test_00_migrations.py`
- `backend/tests/test_notifications.py`
- `mobile/.env.example`
- `mobile/app.json`
- `mobile/package.json`
- `mobile/package-lock.json`
- `mobile/src/app/_layout.tsx`
- `mobile/src/app/assistant.tsx`
- `mobile/src/app/index.tsx`
- `mobile/src/app/notification-settings.tsx`
- `mobile/src/auth.tsx`
- `mobile/src/notifications.ts`
- `mobile/src/notification-routing.js`
- `mobile/src/notification-routing.d.ts`
- `mobile/src/notification-routing.test.mjs`
- `mobile/src/types.ts`
- `docs/part-16-report.md`

## Verification

Commands included:

```powershell
docker compose --profile test rm -sf test-db
docker compose --profile test run --build --rm test
docker compose --profile test run --build --rm test python -m evaluation.runner --json /tmp/part-16-evaluation.json --markdown /tmp/part-16-evaluation.md
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:navigation
npx.cmd expo install --check
npx.cmd expo-doctor
Set-Location ..
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec api alembic current
docker compose exec api alembic check
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
docker compose exec db psql -U wealth_local -d wealth_manager -tAc "SELECT system_identifier FROM pg_control_system();"
curl.exe --fail --silent http://localhost:8000/health/live
curl.exe --fail --silent http://localhost:8000/health/ready
docker compose stop test-db
git diff --check
```

Results:

- Clean disposable migration chain through `20261002_0012`: passed.
- Alembic model check: no new upgrade operations detected.
- Focused notification/authentication tests: **13 passed**.
- Complete backend suite after the conversation-targeted mobile notification update: **106 passed in 23.37 seconds**, with one upstream Starlette TestClient deprecation warning.
- Part 13 offline deterministic evaluation: **14/14 passed**, provider disabled and network access false.
- Multi-device fanout, disabled devices, idempotency, user isolation, device-session revocation, timeout recovery, bounded retry/dead-letter, invalid token handling, ticket/receipt processing, generic payload privacy, log privacy, and financial/assistant mutation invariants: passed with mocked providers.
- Mobile TypeScript and Expo lint: passed.
- Mocked mobile notification navigation: **4/4 passed** for authenticated conversation routing and rejection of unauthenticated, malformed, or unsupported routes.
- `expo install --check`: dependencies up to date.
- Expo Doctor: **21/21 checks passed**.
- Development Alembic state: `20261002_0012 (head)`.
- API-to-PostgreSQL connectivity: passed.
- `/health/live`: `ok`; `/health/ready`: `ok`, database `connected`.
- Development data count before and after migration: `users=0`; notification devices initially `0`.
- PostgreSQL cluster identifier: **`7690665958609113124`**, unchanged.

## Limitations

- No physical device, two-phone fanout, live Expo ticket, live receipt, FCM/APNs credential, emulator notification, or lock-screen display was tested. Provider behavior is mocked in tests.
- Expo, FCM and APNs provide best-effort delivery and no end-device display guarantee.
- The worker uses one-process polling at ten-second intervals and batches at most 100 sends or receipts per pass. Larger deployments need shared rate limiting and operational alerting.
- Dead letters are visible through notification history but there is no administrator console or automatic replay; the user can correct device configuration and create a new intended event.
- Reminder creation is an immediate user-requested informational event. Recurring calendar scheduling is not implemented.
- Notification delivery cannot trade, purchase, make offers, mutate stored financial research, change calculations, or execute assistant output.
