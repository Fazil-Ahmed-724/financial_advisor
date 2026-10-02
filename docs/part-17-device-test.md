# Part 17 two-device validation

Real-device delivery was not performed in this workspace because two configured physical devices and platform push credentials were not available. Use this checklist with one iOS and one Android development build.

1. Set `API_BIND_HOST=0.0.0.0`, use a LAN-reachable `EXPO_PUBLIC_API_URL`, configure the EAS project ID and Android/iOS push credentials, then run `docker compose up -d --build`.
2. Sign into the same account on both phones. On **Notifications and devices**, register each phone, grant OS permission, enable the device, then enable `assistant_response_ready` at user and device level.
3. Confirm diagnostics show both devices active and eligible. Diagnostics deliberately omit Expo tokens.
4. Select both devices, press **Review test notification**, review the selection, then press **Send confirmed test**. Confirm one generic notification per phone and that tapping it opens the authenticated notification screen.
5. In Chat, enable **Notify when ready**, send one question, and confirm one generic notification per eligible phone. Tap each notification and confirm it opens the owned conversation; open citations/evidence and limitations in the app.
6. Repeat the same request/idempotency operation and confirm no duplicate deliveries. Disable one device and repeat; only the enabled phone should receive it. Re-enable it, revoke the other device, and confirm the revoked session is rejected and receives no future fanout.
7. Record OS permission, token registration, API event ID, delivery status, receipt status, tap/deep-link result, foreground/background/terminated behavior, lock-screen redaction, disable result, and revoke result for each phone.

Status meanings: `pending/retry` is queued, `accepted` means Expo accepted the request, `delivered` means a successful provider receipt, `unknown` has no definitive receipt, and `permanent_failure/dead_letter` requires operator or device action. Provider acceptance or a successful receipt does not prove the operating system displayed the notification.

Never paste tokens into this record. Push payloads must contain only event identifiers, an allowlisted route, and for assistant alerts an owned conversation ID. Questions, answers, citations, holdings, balances, tax data, and book text belong behind authenticated APIs.

