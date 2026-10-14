# Phase 3 Test Report

> Historical implementation baseline. The later real-world validation is in [PHASE3_REAL_WORLD_VALIDATION_REPORT.md](PHASE3_REAL_WORLD_VALIDATION_REPORT.md). The credential-free Vietnamese TTS extension is recorded in [FREE_TTS_VALIDATION_REPORT.md](FREE_TTS_VALIDATION_REPORT.md): 118 backend tests and 66 Playwright tests pass; real gTTS/experimental Edge network calls were measured, while credentialed STT/LLM/Google TTS, human voice-quality scoring, YouTube traffic, and OBS recording remain untested.

Date: 2026-10-13  
Environment: Windows, Python 3.14, PostgreSQL 17, Mailpit 1.31.4, Bun 1.3.12, Chromium/Playwright 1.63.0  
Scope: Phase 3 real-voice implementation with deterministic local verification. Phase 4 was not started.

## Final result

- `MOCK_TESTED`: PASS
- `SIMULATED_PROVIDER_TESTED`: PASS
- `REAL_PROVIDER_NOT_TESTED`: pending credentials and billable provider access
- `OBS_NOT_TESTED`: pending OBS Studio desktop verification

## Commands and genuine results

| Command | Result |
|---|---|
| `uv run alembic upgrade head` on a recreated empty `app` database | PASS; all migrations through `c4a7e2b913d1` |
| `uv run alembic downgrade -1` then `uv run alembic upgrade head` | PASS |
| `uv run ruff check app tests` | PASS |
| `uv run mypy app` | PASS; 46 files |
| `uv run ty check app` | PASS |
| `uv run pytest -q` | PASS; 102 tests, 69 warnings |
| `bun run lint` | PASS; 86 files |
| `bun run build` | PASS; TypeScript and Vite production build |
| `bunx playwright test tests/live-character.spec.ts tests/login.spec.ts` | PASS; 11/11 in 43.7 s with 2 workers |
| `bun run test` on a freshly migrated database | PASS; 64/64 in 1.8 min with 2 workers |
| `uv run python scripts/benchmark_voice_simulated.py` | PASS; 20 iterations |
| `python harness/validate_pack.py` | PASS; documentation, 6 skills, 8 scenario fixtures |
| `uv lock --check` and `bun install --frozen-lockfile` | PASS; lockfiles are consistent |
| `uvx pip-audit --path D:\\kira_ai\\.venv\\Lib\\site-packages` | PASS; no known vulnerabilities; local `app` package skipped |
| `bun audit` | PASS; no vulnerabilities |
| Frontend source/build provider-secret scan | PASS; no provider secret names or key-shaped values |

The production build reports only the known lazy `AvatarScene` chunk-size warning. Test warnings include intentionally weak local template secrets, an upstream Pipecat Google TTS base-class deprecation, and a Google dependency Python deprecation.

## Automated behavior coverage

- Binary PCM protocol bounds, direction, UUID, and round-trip parsing.
- Mic turn ordering, duplicate/out-of-order frame drops, final transcript emission, and no raw-audio persistence path.
- Bounded Vietnamese context and separation of untrusted chat/donation text from system instructions.
- Streaming LLM-to-clause-to-TTS flow, first-audio timing, usage accounting, fallback labeling, and cancellation stopping further audio.
- Real mode rejection when backend provider credentials are incomplete.
- Mock dashboard -> transcript/chat/donate -> Director -> FakeLLM -> FakeTTS -> WebSocket -> Web Audio -> 3D overlay.
- Exactly one playback start, talking/idle transitions, immediate mute cancellation, stop revocation, reconnect without stale replay, paid-event handling, priority, and prompt-injection rejection.
- YouTube Phase 2 OAuth/event tests and upstream template auth/CRUD/email tests remained green.

## Simulated latency

The benchmark output was:

```json
{
  "measurement_scope": "SIMULATED_PROVIDER_LOCAL",
  "iterations": 20,
  "event_to_first_audio_ms": { "p50": 219.113, "p95": 221.201 },
  "cancellation_ms": 0.698,
  "real_providers_called": false,
  "obs_called": false
}
```

These numbers measure local simulated adapters only. They do not establish Deepgram/OpenAI/Google or OBS latency and must not be compared to the real-provider target as a PASS.

## Failures observed and fixed during stabilization

- Playwright initially timed out while the eager 1 MB Three/VRM module and a 60 FPS scene competed with auth pages. The renderer is now lazy-loaded and demand-rendered at 10 FPS idle / 20 FPS speaking.
- Headless Web Audio occasionally delayed `onended`. Playback now has an idempotent duration-based watchdog that stops the source and emits one completion ACK if the normal callback stalls.
- A short mock tone could finish before the browser delivered the mute click under CPU contention. The tone is six seconds with larger chunks, preserving a deterministic cancellation window without increasing message count.
- A repeated local run retained an active session and duplicate test users. The final reported suite used a recreated, migrated test database; no test was skipped and worker count stayed at two.
- An existing Items locator matched both `Items` and `You don't have any items yet`; the assertion now uses an exact accessible name, making it stricter rather than weakening coverage.
- `bun audit` initially reported one low Babel source-map advisory. The compatible patched `@babel/core` 7.29.7 is pinned and the final audit is clean.
- `.env`, local virtual environments, and `.tmp` services/data are now ignored while `.env.example` remains tracked.

## Pending external checks

No Deepgram, OpenAI, Google Cloud TTS, real YouTube channel, microphone hardware acceptance run, or OBS Studio process was available. Follow `docs/17_PHASE3_VOICE_RUNBOOK.md` for credentialed voice verification and `docs/15_MANUAL_OBS_TEST_GUIDE.md` for OBS transparency/audio routing.
