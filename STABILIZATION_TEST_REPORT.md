# Phase 1 Stabilization Test Report

Date: 2026-10-12  
Scope: Phase 0–1 `MOCK_ONLY`  
Result: PASS for the automated mock MVP; manual OBS desktop verification remains PENDING.

## What was stabilized

1. Mailpit v1.31.5 was started on SMTP `1025` and HTTP `8025`. Its Windows binary matched the release's published SHA-256 (`9637e21c02b33185fe69268ba05317152a5d8ac7877115e8a70e29b7e199e8dc`).
2. The upstream signup test helper now waits for the signup HTTP response before navigating. This removed the password-recovery race seen under parallel Playwright load.
3. Paid events queued during playback now drain in order and are spoken once.
4. Overlay playback now rejects duplicate lifecycle events, cancels buffered/current audio immediately, reports playback/cancellation measurements, and does not replay completed audio after reconnect.
5. The E2E test now proves transparent rendering, overlay-only audio ownership, talking/idle state, single playback, mute/stop, prompt-injection rejection, paid response, telemetry, reconnect, and stopped-key revocation.
6. WebSocket ticket/key query values are redacted in Uvicorn logs, including rejected and disconnected connections.

## End-to-end acceptance evidence

| Requirement | Automated evidence | Result |
|---|---|---|
| Login, character create, session start | `frontend/tests/live-character.spec.ts` | PASS |
| Voice -> director -> FakeLLM -> FakeTTS -> WebSocket -> overlay | Browser E2E plus backend integration tests | PASS |
| Chat is lower priority and untrusted | Prompt-injection E2E and director tests | PASS |
| Donation queue handling | Backend queue-drain test and paid-response E2E | PASS |
| Priority P0 > P1 > P2 > P3 | Director scenario fixtures | PASS |
| PCM plays exactly once | Playback-start count asserted in Chromium | PASS |
| 3D talking -> idle | Overlay state attributes asserted in Chromium | PASS |
| Immediate mute and stop | Cancellation event/ACK and key revocation asserted | PASS |
| Reconnect without stale replay | Reload playback count remains unchanged | PASS |
| Transparent browser source | Computed alpha on `html`, `body`, and overlay asserted | PASS |
| Single audio route | Overlay identifies itself as owner; Dashboard has no audio element | PASS |
| Real OBS Browser Source | Manual guide created; no OBS installation available | PENDING |

## Commands and genuine results

| Command | Exit | Result |
|---|---:|---|
| `uv run alembic upgrade head` from an empty PostgreSQL database | 0 | schema upgraded to head |
| `uv run ruff check backend` | 0 | PASS |
| `uv run mypy backend/app` | 0 | no issues in 37 source files |
| `uv run ty check backend/app` | 0 | PASS |
| `uv run pytest` | 0 | 78 passed, 61 warnings, 12.26 s |
| `npx -y bun@1.3.12 run lint` | 0 | 83 files checked |
| `npx -y bun@1.3.12 run build` | 0 | production build created; chunk warning only |
| focused Playwright setup + live-character test | 0 | 2 passed, 32.3 s |
| focused password-reset group | 0 | 7 passed, 14.2 s |
| `npx -y bun@1.3.12 run test` | 0 | 63 passed, 1.9 min |
| `python harness/validate_pack.py` | 0 | docs + 6 skills + 8 scenarios valid |
| frozen production requirements -> `pip-audit` | 0 | no known vulnerabilities; local app skipped as non-PyPI |
| `npx -y bun@1.3.12 audit` | 1 | one low transitive Babel advisory; no moderate/high/critical |
| high-signal credential pattern scan | 0 | no committed-looking provider secrets detected |

The full Playwright run was performed with real local PostgreSQL 17, FastAPI, official Mailpit, and Chromium services. No test was skipped, quarantined, or changed to accept a failure.

## Telemetry results

The backend keeps bounded, content-free measurements and exposes summaries to the authenticated Dashboard. The E2E test confirms the values reach the UI. `trace_id` joins server decisions, generated audio, overlay ACKs, and cancellation ACKs without recording message or audio content.

| Metric | Samples | P50 ms | P95 ms |
|---|---:|---:|---:|
| event-to-decision | 9 | 0.565 | 0.885 |
| FakeLLM | 4 | 0.003 | 0.005 |
| FakeTTS first audio | 4 | 229.819 | 644.886 |
| overlay playback ACK | 4 | 315.114 | 465.361 |
| event-to-first-playback ACK | 4 | 694.179 | 984.635 |
| client first-chunk-to-playback | 4 | 278.2 | 430.2 |
| cancellation dispatch | 2 | 0.334 | 0.355 |
| cancellation request-to-ACK | 1 | 44.843 | 44.843 |
| client audio stop | 1 | 0.0 | 0.0 |

Measurement label: `MOCK_SIMULATED_LOCAL`. These are development measurements of fake processing plus local Chromium transport/playback. They must not be used as real STT, LLM, TTS, network, voice-turn, or OBS benchmarks.

## Environment

- Windows, PowerShell
- Python 3.14.7
- PostgreSQL 17.10
- Mailpit 1.31.5
- Bun 1.3.12
- Playwright 1.63.0, Chromium
- Upstream template baseline: commit `7257e6067bc4b42f1c7ada205301a33410dce4a8`

## Remaining work before an OBS release

Run `docs/15_MANUAL_OBS_TEST_GUIDE.md` on the intended streaming PC and record:

- OBS version, browser-source resolution/FPS, CPU/GPU/RAM, and dropped frames;
- alpha compositing over a real scene;
- one and only one recording/mixer audio path;
- mute/stop audible latency samples;
- refresh/reconnect without replay.

This is the only pending Phase 1 environment verification. Real providers, YouTube, microphone/VAD, and distributed Redis transport are Phase 2+ and were intentionally not started.
