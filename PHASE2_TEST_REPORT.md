# Phase 2 Test Report

Date: 2026-10-12

## Result

Phase 2 is `AUTOMATED_MOCK_TESTED` and ready for a credentialed YouTube acceptance run. The offline Phase 0–1 path remains green. No real Google account/channel or OBS Studio was available, so neither is reported as tested.

## Executed checks

| Command | Result |
|---|---|
| `uv run alembic upgrade head` against a new temporary PostgreSQL database | PASS — all template, Phase 1, and Phase 2 migrations reached `b2f14b7ca902 (head)` |
| `cd backend; uv run pytest` | PASS — 95 passed, 67 warnings, 9.26 s |
| `cd backend; uv run ruff check .` | PASS |
| `cd backend; uv run mypy app` | PASS — 39 source files |
| `cd backend; uv run ty check app` | PASS |
| `cd frontend; npm run lint` | PASS — 85 files |
| `cd frontend; npm run build` | PASS — production bundle built; large Three.js/avatar chunk warning only |
| `cd frontend; npx playwright test --reporter=line` with FastAPI, PostgreSQL, Vite, and Mailpit running | PASS — 64 passed in 2.2 minutes |
| `python harness/validate_pack.py` | PASS — documentation, 6 skills, 8 scenario fixtures |
| `uv export --package app --no-dev --no-emit-project --no-hashes` then `pip-audit` | PASS — no known vulnerabilities |
| `bun audit` | PARTIAL — one low transitive `@babel/core` advisory; 0 critical/high/moderate |
| High-signal repository credential-pattern scan excluding local `.env`, dependency, and report directories | PASS — no Google API key, Google client-secret prefix, or private-key block found |

Warnings were not hidden: Pytest reports template development-secret/JWT-key warnings plus Starlette's `TestClient` deprecation warning. The frontend build reports the existing large Three.js/avatar chunk. They do not fail the current gates.

## Behaviors covered automatically

- OAuth authorization URL, PKCE S256, one-use expiring state, safe callback, encrypted token storage, refresh-state behavior, revoke/delete disconnect, and auth-required routes.
- Owned active-broadcast selection and rejection of inactive/unowned IDs.
- Text, Super Chat, and Super Sticker mapping with exact micros/currency/display values.
- Initial history suppression, durable message-ID deduplication, checkpoint resume, and no historical paid-event acknowledgment.
- Stream-first ingestion, list fallback with provider polling interval, bounded reconnect, and terminal quota handling.
- Untrusted YouTube text cannot become control events or bypass the Conversation Director.
- Existing Dashboard -> Director -> FakeLLM -> FakeTTS -> WebSocket -> overlay behavior, including exactly-once playback, talking/idle state, mute/stop cancellation, and reconnect without stale audio.
- YouTube settings/dashboard show honest disconnected/not-configured state while Mock Mode remains usable.

## Not executed

- `REAL_YOUTUBE_NOT_TESTED`: no real Google OAuth consent, channel, livestream, messages, Super Chat, Super Sticker, refresh, or quota measurement.
- `OBS_NOT_TESTED`: no OBS Studio browser-source capture, mixer-routing, or recording test.
- Phase 3 providers were deliberately not added or tested.

Use [docs/16_PHASE2_YOUTUBE_RUNBOOK.md](docs/16_PHASE2_YOUTUBE_RUNBOOK.md) for the real-channel checklist and [docs/15_MANUAL_OBS_TEST_GUIDE.md](docs/15_MANUAL_OBS_TEST_GUIDE.md) for OBS verification.
