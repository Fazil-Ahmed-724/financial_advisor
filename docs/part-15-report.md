# Part 15 implementation and verification

Verified October 2, 2026 (Asia/Karachi).

Part 15 adds supervised, user-controlled review of specific assistant responses. It reuses the existing Part 13 `assistant_response_reported` audit-event storage and endpoint instead of adding a second feedback model. No database schema change was needed, so no migration was created; Alembic remains at `20261001_0011`. The development PostgreSQL volume and existing data were preserved.

## Feedback and personal review workflow

The fixed categories are `helpful`, `inaccurate`, `unsupported`, `stale`, `confusing`, and `missing_evidence`. An optional note is normalized and limited to 500 characters. One active report is allowed per owned assistant response; another submission returns HTTP 409 and directs the user to update the existing report.

The application has no reviewer or administrator role. Review is therefore a private personal inbox rather than a simulated administrator queue. Every create, list, update, delete, and export query includes the authenticated user ID. The response owner may mark a report `submitted`, `reviewed`, or `dismissed`, add a bounded review annotation, select a reviewed report for fixture export, or delete the feedback record. Deletion affects only the feedback event and cannot delete the assistant message or any financial record.

Each report preserves the response mode, citation record IDs, citation source dates and types, freshness labels, deterministic calculation service names, citation count, validation status, and fallback status. It does not copy the prompt, answer, excerpts, book passages, source text, financial amounts, credentials, or provider tokens. Feedback has `financial_action: false` and cannot invoke ledger, trade, tax, property, marketplace, provider-configuration, or model-training operations.

The mobile assistant evidence view now includes **Report response**, the six categories, an optional note, and a privacy statement. A separate feedback history screen shows status, category, date, mode, citation count, source dates, freshness, review controls, selection, deletion, and a two-step export confirmation.

## Sanitized regression export

`POST /assistant/feedback/export` accepts an explicit list of feedback IDs and the literal confirmation `confirm_sanitized_export: true`. Every selected report must belong to the caller, have status `reviewed`, and have `fixture_selected: true`.

The `assistant-feedback-regression-v1` output contains synthetic sequential case IDs and only behavioral metadata: normalized category, expected behavior, response mode, source types, freshness labels, citation count, deterministic service names, validation status, and fallback status. It excludes database IDs, user identifiers, message IDs, comments, prompts, answers, balances, account numbers, source passages, and secrets. Export creates a candidate for manual regression-test implementation; it does not modify the checked-in Part 13 dataset, train or fine-tune a model, alter prompts, or change provider settings.

Legacy Part 13 categories remain readable and are mapped to the closest Part 15 category. Newly submitted reports use only the Part 15 fixed set.

## API changes

- `POST /assistant/messages/{message_id}/feedback` — create one report for an owned assistant response.
- `GET /assistant/feedback` — list the caller's private feedback inbox.
- `PUT /assistant/feedback/{feedback_id}` — update category, note, review status, review annotation, or fixture selection.
- `DELETE /assistant/feedback/{feedback_id}` — delete the caller's feedback report.
- `POST /assistant/feedback/export` — explicitly export reviewed and selected reports in sanitized form.

## Changed files

- `README.md`
- `backend/app/routes_assistant.py`
- `backend/app/schemas_assistant.py`
- `backend/tests/test_assistant_feedback.py`
- `mobile/src/types.ts`
- `mobile/src/app/_layout.tsx`
- `mobile/src/app/assistant.tsx`
- `mobile/src/app/assistant-evidence.tsx`
- `mobile/src/app/assistant-feedback.tsx`
- `docs/part-15-report.md`

No model, migration, dependency, provider adapter, financial calculation service, or Part 13 evaluation case was changed.

## Verification

Commands:

```powershell
docker compose --profile test run --build --rm test python -m evaluation.runner --json /tmp/part-13-regression.json --markdown /tmp/part-13-regression.md
docker compose --profile test run --build --rm test
Set-Location mobile
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo install --check
npx.cmd expo-doctor
Set-Location ..
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec api alembic current
docker compose exec api alembic check
docker compose exec db psql -U wealth_local -d wealth_manager -tAc "SELECT system_identifier FROM pg_control_system();"
curl.exe --fail --silent http://localhost:8000/health/live
curl.exe --fail --silent http://localhost:8000/health/ready
docker compose stop test-db
git diff --check
```

Results:

- Part 13 offline deterministic evaluation: **14/14 passed**, preserving the required baseline with the provider disabled and no provider network access.
- Synthetic reviewed-feedback export tests: passed; explicit review, selection, and confirmation are required, and personal/source text, IDs, amounts, and secrets are absent.
- Complete backend suite on a clean disposable database: **100 passed** in 24.78 seconds, with one upstream Starlette TestClient deprecation warning.
- Clean migration chain through `20261001_0011`: passed.
- Ownership, duplicate conflict, update, deletion, category validation, text bounds, legacy-category handling, log privacy, mutation invariants, and provider-setting invariants: passed.
- Mobile TypeScript: passed.
- Expo lint: passed.
- `expo install --check`: dependencies up to date.
- Expo Doctor: **21/21 checks passed**.
- Compose configuration: valid.
- Development Alembic state: `20261001_0011 (head)`; `alembic check` reported no new upgrade operations.
- API and development PostgreSQL containers: healthy.
- `/health/live`: `ok`; `/health/ready`: `ok`, database `connected`.
- PostgreSQL cluster ID: **`7690665958609113124`**, unchanged.
- The disposable test database was stopped after verification.
- `git diff --check`: passed; Git reported only expected LF-to-CRLF working-tree notices on Windows.

No model download, live inference server, emulator, or physical-device test was performed.

## Remaining limitations

- A selected export is a sanitized candidate. A developer must inspect it and deliberately implement it as a synthetic checked-in test before it affects the regression suite.
- Personal review status reflects the user's own assessment. The application has no independent reviewer/admin role or multi-person approval process.
- Reports retain citation IDs and metadata but intentionally omit full conversation and source content, so detailed investigation may require opening the still-retained owned conversation and records.
- Deleting a conversation may remove the context needed to inspect a retained feedback event; the report itself remains privacy-minimized metadata until the user deletes it.
- Passing tests and evaluation cases do not demonstrate that feedback improved model quality, that generated output is independently verified, or that any explanation is suitable financial, tax, or legal advice.
