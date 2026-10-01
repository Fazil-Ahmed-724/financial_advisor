# Part 14 implementation and verification

Verified October 1, 2026 (Asia/Karachi).

Part 14 adds optional local OpenAI-compatible inference to the Part 12/13 read-only assistant. It introduces no persistent entity or column. No migration was needed or created; Alembic remains at `20261001_0011`. The development PostgreSQL volume and data were preserved.

## Provider design

`ASSISTANT_PROVIDER=disabled` remains the default. `local_openai_compatible` selects the new local adapter, while the existing external `openai_compatible` adapter remains available for backward compatibility.

The local adapter calls `{ASSISTANT_LOCAL_PROVIDER_URL}/chat/completions` using the OpenAI-compatible chat shape. It requires a separately installed and explicitly selected model. API startup never installs inference software, downloads weights, pulls a model, or calls a paid service.

The local URL is restricted to `localhost`, `127.0.0.1`, `::1`, or `host.docker.internal`. User information, query strings, URL credentials, unsupported schemes, redirects, and environment HTTP proxies are rejected or disabled for these calls. Local requests have no authorization header by default. The application adds no telemetry.

Configurable limits and safe defaults:

| Variable | Default | Enforced range/purpose |
| --- | ---: | --- |
| `ASSISTANT_MAX_CONTEXT_CHARS` | 12000 | Existing retrieved-evidence character bound |
| `ASSISTANT_MAX_OUTPUT_CHARS` | 12000 | Existing validated answer bound |
| `ASSISTANT_PROVIDER_TIMEOUT_SECONDS` | 15 | 1–60 seconds |
| `ASSISTANT_PROVIDER_MAX_CONCURRENCY` | 2 | 1–8 in-process calls |
| `ASSISTANT_PROVIDER_MAX_REQUEST_BYTES` | 65536 | 4 KiB–256 KiB |
| `ASSISTANT_PROVIDER_MAX_RESPONSE_BYTES` | 32768 | 1 KiB–128 KiB |

## Safety boundary

The model receives only the already-authorized question, deterministic evidence draft, and bounded citation bundle. It receives no database session, shell, network-browser, mutation, trading, purchasing, listing, or property-offer tool.

Existing application services remain responsible for all retrieval, ownership checks, FIFO values, gains, fees, tax estimates, yields, margins, evidence dates, and freshness labels. Generated text must preserve the deterministic draft's complete citation-marker multiset and numeric-token multiset. The Part 13 structured validator then verifies the exact ordered citation records, calculation references, freshness fields, response schema, and output bounds.

Connection failures, timeouts, concurrency saturation, oversized payloads, malformed JSON, missing fields, fabricated markers, changed numbers, invalid provider configuration, and validation failures all return the deterministic evidence answer. Mobile clients receive only a generic fallback limitation; internal URLs, request content, and provider errors are not returned or logged.

Retrieved books, reviewed CSV imports, marketplace text, and property source/description data remain untrusted. Tests confirm their embedded instructions remain cited data and are not executed.

## Separate Ollama setup

Ollama is one supported OpenAI-compatible local server. It is installed and operated outside Compose. The operator must explicitly choose and pull a model:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
# Restart Ollama after changing user environment variables.
ollama pull <model-name>
ollama list
```

Root `.env`:

```dotenv
ASSISTANT_PROVIDER=local_openai_compatible
ASSISTANT_LOCAL_PROVIDER_URL=http://host.docker.internal:11434/v1
ASSISTANT_LOCAL_PROVIDER_MODEL=<model-name>
ASSISTANT_PROVIDER_TIMEOUT_SECONDS=15
ASSISTANT_PROVIDER_MAX_CONCURRENCY=2
ASSISTANT_PROVIDER_MAX_REQUEST_BYTES=65536
ASSISTANT_PROVIDER_MAX_RESPONSE_BYTES=32768
```

Apply configuration with `docker compose up --build -d --wait`. Firewall access to port 11434 should remain limited to the local machine or trusted private network. Model licenses and hardware requirements vary. Model files may require tens to hundreds of GB; context length and parallelism raise RAM/VRAM use, and CPU inference may be slow. The project does not select a model or claim one is adequate for financial explanations.

References: [Ollama Windows](https://docs.ollama.com/windows) and [Ollama FAQ](https://docs.ollama.com/faq).

## Changed files

- `.env.example`
- `compose.yaml`
- `backend/app/assistant_provider.py`
- `backend/app/assistant_service.py`
- `backend/tests/test_local_assistant_provider.py`
- `README.md`
- `docs/part-14-report.md`

No mobile source file, dependency, database model, or migration changed.

## Verification

Commands:

```powershell
docker compose --profile test run --build --rm test python -m evaluation.runner --json /tmp/part-13-regression.json --markdown /tmp/part-13-regression.md
docker compose --profile test rm -sf test-db
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
docker compose exec api python -c "from app.database import check_database; check_database(); print('PostgreSQL connection OK')"
docker compose exec db psql -U wealth_local -d wealth_manager -tAc "SELECT system_identifier FROM pg_control_system();"
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
docker compose --profile test stop test-db
git diff --check
```

Results:

- Part 13 offline deterministic evaluation: **14/14 passed**, provider disabled and no provider network access.
- Clean disposable-database migration chain through `20261001_0011`: passed.
- Complete backend suite: **96 passed**, with one upstream Starlette TestClient deprecation warning.
- Mocked local-provider coverage: successful generation, timeout/unreachable provider, malformed responses, fabricated citations, changed numeric values, output bounds, nonlocal URL rejection, deterministic fallback, cross-user exclusion, and injection content from books, CSV imports, marketplace text, and property records.
- Mobile TypeScript: passed.
- Expo lint: passed.
- `expo install --check`: dependencies up to date.
- Expo Doctor: **21/21 checks passed**.
- Compose configuration: valid.
- Development Alembic state: `20261001_0011 (head)`; `alembic check` reported no new upgrade operations.
- API-to-PostgreSQL connection: passed.
- API and development PostgreSQL containers: healthy.
- `/health/live`: `ok`; `/health/ready`: `ok`, database `connected`.
- PostgreSQL cluster ID: **`7690665958609113124`**, unchanged from Parts 11–13.
- Disposable test database stopped after verification.

No model was downloaded and no live inference server, external model, emulator, or physical device was tested.

## Remaining risks and limitations

- Mocked tests prove adapter behavior and validation paths, not the language quality, latency, hardware compatibility, or stability of any model.
- Local model output is not independently verified. Citations show the records supplied to generation; they do not prove that an explanation or recommendation is suitable.
- Exact numeric preservation is deliberately strict. A local model that omits, reformats, or adds a number will trigger deterministic fallback even when its prose might otherwise be acceptable.
- Concurrency control is process local. The current Compose deployment runs one Uvicorn process; a future multi-worker deployment must enforce a shared provider limit separately.
- Host firewall and Ollama configuration remain operator responsibilities. Enabling cloud models or web search in inference software would change the privacy boundary outside this application's control.
- No output is a guaranteed return, personalized regulated investment instruction, legal opinion, or official tax determination.
