# Phase 3 Real-World Validation Report

> Historical credential-gated validation baseline. Credential-free gTTS and experimental Edge TTS were added and tested later; see [FREE_TTS_VALIDATION_REPORT.md](FREE_TTS_VALIDATION_REPORT.md). This report's `REAL_PROVIDER_NOT_TESTED` statements refer to the earlier Deepgram/OpenAI/Google Cloud environment.

Date: 2026-10-13  
Environment: Windows, Python 3.14.7, PostgreSQL 17, Mailpit 1.31.4, Node/npm, Chromium/Playwright 1.63.0  
Scope: validate and harden Phase 3 only. Phase 4 was not started.

## Verdict

- `MOCK_TESTED`: PASS.
- `SIMULATED_PROVIDER_TESTED`: PASS.
- `PREFLIGHT_TESTED`: PASS.
- `REAL_PROVIDER_NOT_TESTED`: blocked by missing Deepgram, OpenAI, and Google Cloud credentials.
- `REAL_YOUTUBE_NOT_TESTED`: blocked by missing Google OAuth credentials and a permitted live channel.
- `MIC_NOT_TESTED`: no human browser-permission/speech run was performed.
- `OBS_NOT_TESTED`: OBS Studio is installed, but it was not running and no recording was made.

The application is ready for a credentialed operator run, but this report does **not** claim real Vietnamese quality, provider latency, provider cancellation, billing accuracy, or OBS audio routing.

## Environment preflight

Only booleans and file existence were inspected; no secret values were printed.

| Check | Observed |
|---|---|
| `DEEPGRAM_API_KEY` configured | No |
| `OPENAI_API_KEY` configured | No |
| Google credential reference configured | No |
| Google credential file readable | No |
| All cost-rate variables configured | No |
| YouTube OAuth backend configured | No |
| Windows audio devices visible | Yes; this does not prove a working microphone |
| OBS installed at standard path | Yes |
| OBS process running / recording tested | No |

## Issues found and fixed

1. End-to-end timing previously started at final transcript receipt. It now carries the server-side browser-VAD-end timestamp through STT and records `stt_final_ms` plus `voice_end_to_first_playback_ack_ms` on the same monotonic clock.
2. Local fallback audio could contaminate real-provider aggregate latency. Affected traces are now `DEGRADED_FALLBACK_LOCAL`; their trace values remain visible but are excluded from real P50/P95.
3. A non-empty but missing Google credential path previously looked configured. Real sessions now require a readable credential file.
4. The default `gpt-5-mini` is deprecated in current official OpenAI documentation. The compatible low-latency default is now `gpt-5.4-mini`; it remains environment-configurable.
5. OpenAI Responses requests now set `store=false`.
6. Usage now reports per-counter provenance and observed session duration, and can extrapolate a 3-hour cost only for Voice Real, after 60 seconds, with all operator-supplied rates present. Disconnected STT frames are excluded; Mock usage never produces a real cost projection.
7. Added `/settings/diagnostics` and authenticated `/api/v1/diagnostics/phase3`. They expose readiness/model IDs only—never keys, tokens, or credential paths.

## Commands actually executed

| Command | Result |
|---|---|
| Environment boolean/file/process/device preflight | PASS; blockers listed above |
| `uv run ruff check app tests` | PASS |
| `uv run mypy app` | PASS; 47 source files |
| `uv run ty check app` | PASS |
| `uv run pytest -q` | PASS; 110 tests, 73 warnings |
| `npm run lint` | PASS; 88 frontend files |
| `npm run build` | PASS; TypeScript + production Vite build; known 3D chunk warning only |
| `npx playwright test --project=chromium --reporter=line` with Mailpit | PASS; 65/65 tests in 1.7 minutes on the final code |
| `uv run python scripts/benchmark_voice_simulated.py` | PASS; result below |
| `python harness/validate_pack.py` | PASS; 6 skills and 8 fixtures; documentation validation only |
| `uv run alembic upgrade head` from `backend/` | PASS |
| `uv lock --check` | PASS |
| `uvx pip-audit --path D:\kira_ai\.venv\Lib\site-packages` | PASS; no known vulnerabilities; local `app` skipped as non-PyPI |
| `npx -y bun@1.3.12 audit` | PASS; no vulnerabilities |
| Key-shaped secret and frontend `VITE_*` provider-secret scan | PASS |

One operational retry was needed: Playwright authentication initially failed after pytest intentionally deleted test users during fixture teardown. Running `uv run python app/initial_data.py` restored the local superuser; the complete 65-test suite then passed without skipping or weakening tests. A first Alembic invocation from the repository root reported no `script_location`; the documented invocation from `backend/` passed.

## Automated behavior evidence

The regression suite covers the full Mock path: dashboard → mock transcript/chat/donate → Conversation Director → FakeLLM → FakeTTS → WebSocket → Web Audio → procedural 3D overlay. It asserts exactly-once playback, talking/idle state, mute and stop cancellation, reconnect without stale replay, donation queueing/deduplication, priority, prompt-injection rejection, transparency, overlay-only audio ownership, OAuth security, and YouTube reconnect/quota/dedupe behavior using fixtures.

Additional validation tests cover:

- authenticated diagnostic access and absence of provider secrets/credential paths;
- rejection of an unreadable Google credential file;
- VAD-end → STT-final → overlay-ACK metric propagation;
- fallback trace exclusion from real-provider P50/P95;
- OpenAI `store=false`;
- Voice Real-only 3-hour cost projection rules.

These are implementation and simulation tests. They are not evidence that real vendors or OBS worked.

## Latency and cost

No real latency distribution or real cost was measurable because provider credentials were absent. Therefore real P50, P95, STT, LLM, TTS-first-audio, cancellation, and 3-hour cost are all `NOT_TESTED`/`UNAVAILABLE`.

The local simulated benchmark, run in this validation pass, was:

```json
{
  "measurement_scope": "SIMULATED_PROVIDER_LOCAL",
  "iterations": 20,
  "event_to_first_audio_ms": { "p50": 219.031, "p95": 223.048 },
  "cancellation_ms": 0.339,
  "real_providers_called": false,
  "obs_called": false
}
```

Do not compare these simulated numbers with the real target as a PASS.

## Current official API check

Checked on 2026-10-13:

- Deepgram documents Nova-3 streaming and Vietnamese `vi`: <https://developers.deepgram.com/docs/models-languages-overview>.
- Deepgram documents streaming endpointing, interim results, and `utterance_end_ms`: <https://developers.deepgram.com/reference/speech-to-text/listen-streaming>.
- OpenAI documents `gpt-5.4-mini`, Responses API support, and streaming: <https://developers.openai.com/api/docs/models/gpt-5.4-mini> and <https://developers.openai.com/api/docs/guides/streaming-responses>.
- Google documents Chirp 3 HD streaming PCM, Vietnamese `vi-VN`, and `vi-VN-Chirp3-HD-Leda`: <https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd> and <https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types>.
- YouTube documents `streamList`, `list`, Super Chat, and Super Sticker resources: <https://developers.google.com/youtube/v3/live/docs/liveChatMessages>.

Documentation compatibility does not prove account access, quota, billing, or runtime success.

## How to complete the blocked real run

1. Configure backend credentials and current operator rates from `.env.example`; keep credential files outside the repository.
2. Restart backend, sign in, and open `/settings/diagnostics`. All three voice providers must show ready.
3. Run the local mic test while speaking through the intended headset.
4. Create Voice Real, start it, and open its one-time overlay URL in an OBS Browser Source.
5. Run the Vietnamese/slang/personality set in `docs/17_PHASE3_VOICE_RUNBOOK.md` for at least 30 turns and 60 seconds.
6. Test barge-in, Mute, Stop, dashboard reconnect, Browser Source reload, feedback leakage, and duplicate playback.
7. Paste the session UUID into diagnostics, verify provider health, export evidence JSON, and record P50/P95 plus usage and 3-hour projection.
8. Complete `docs/15_MANUAL_OBS_TEST_GUIDE.md` and retain a short OBS recording proving transparency and exactly-once audio.
9. Connect a permitted YouTube test channel and verify chat, Super Chat, and Super Sticker delivery; do not substitute fixture results.

Until those steps are executed with real credentials/hardware, all external acceptance gates remain pending.
