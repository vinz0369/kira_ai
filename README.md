# AI Live Character

Phase 0–3 are implemented on the FastAPI Full Stack Template. Offline Mock Mode remains available, Phase 2 supplies an optional real YouTube source, and Phase 3 offers selectable FPT Marketplace or OpenAI LLMs with Deepgram STT and gTTS by default.

The tested flow is:

`login -> create character -> mock/YouTube events + browser mic -> Conversation Director -> Fake, FPT or OpenAI LLM -> Fake, gTTS, experimental Edge TTS, or Google Chirp 3 HD -> WebSocket -> animated 3D overlay`

The browser overlay is the only AI-audio output. New characters use the operator-supplied **Arcana** VRM when running locally in development. Existing Kira records using the old sample ID resolve to Arcana without altering their persona, memory or voice; other custom avatar IDs remain untouched. Arcana's embedded terms prohibit redistribution and commercial use, so it stays in `assets/Arcana.vrm`, is Git-ignored, and is served only to an authenticated loopback preview or a valid local overlay session. A deployed/public build falls back to the procedural avatar until the creator grants suitable rights. The old sample file was retired from the public bundle. Idle, speech lip-sync, blink, expressions and hand/head gestures remain; Studio and Control Room use the private local **2 Phút Hơn** VMD when available and retain the CC0 Quaternius `Dance_Loop` as fallback. The `.warudo` file is a Unity/Warudo character mod, not a browser animation clip; it remains local and is not loaded by Three.js. See [asset license register](assets/LICENSE_REGISTER.md) and [OBS test guide](docs/15_MANUAL_OBS_TEST_GUIDE.md).

In Character Studio, choose the default **Từ ngực lên** or **Toàn thân** view, adjust the zoom slider, and save; the same per-character framing is sent to the OBS overlay. Preview natural idle, expressions, **Vẫy tay chào**, and **Tạo hình trái tim** there. Local development also shows **Dance 2 Phút Hơn (local)**: it retargets the operator-supplied 30-second VMD wrist-fix loop to the VRM humanoid and repeats it five times for the existing 150-second control. Retargeting uses the normalized VRM rest pose, proportional Center movement, and bounded foot-IK correction so the Arcana rig does not inherit idle arm offsets or leave its feet behind. Its readme prohibits commercial use, so the VMD is private/local only; the supplied WAV is deliberately not served or played. If the private VMD cannot load, the CC0 Quaternius dance remains the fallback. Pause, Stop, overlay disconnect, or reconnect clears transient motion.

To preview Arcana on this PC, keep `FASTAPI_ENV=development`, place the supplied `Arcana.vrm` in `assets/`, and open Studio or the local OBS overlay. The model's embedded terms prohibit redistribution and commercial use, so do not publish the VRM or use it commercially without written permission from its creator; public builds fall back to the procedural avatar. See [asset license register](assets/LICENSE_REGISTER.md) and [OBS test guide](docs/15_MANUAL_OBS_TEST_GUIDE.md).

## Run locally with Docker

Requirements: Docker with Compose.

1. Keep `MOCK_MODE=true` in `.env`.
2. Start the template stack:

   ```powershell
   docker compose watch
   ```

3. Open <http://localhost> and sign in with the local development account from `.env`.
4. Open **Character Studio** and create a character.
5. Open **Phiên live**. Choose the event source (**Demo** or **YouTube thật**) and voice pipeline (**Voice Mock** or **Voice Real**) separately, then select the character. Review the summary before creating a draft.
6. In the new control room, press **Start**. Copy that session's private overlay URL into an OBS Browser Source. Use the source dimensions shown in the control room and configure browser-source audio monitoring for your stream.
7. **Mute** silences AI without ending the session. **Stop** asks for confirmation, cancels audio and revokes that session's overlay URL. A new session needs a new OBS Browser Source URL.

Development services are also exposed directly: API `http://localhost:8000`, PostgreSQL `localhost:5432`, Redis `localhost:6379`, Mailpit `http://localhost:8025`.

## Run without the full Docker stack

Use Docker for PostgreSQL, Redis, and Mailpit, then run the app processes on the host:

```powershell
docker compose up -d db redis mailpit
cd backend
uv sync
uv run alembic upgrade head
uv run python app/initial_data.py
uv run fastapi dev app/main.py
```

In a second terminal:

```powershell
cd frontend
npx -y bun@1.3.12 install
npx -y bun@1.3.12 run dev
```

Open <http://localhost:5173>.

### Finding the right live session

`/live` separates the one **running/paused** session from recent **drafts** and **ended** sessions. Open the running session instead of creating another draft. A draft can be resumed; an ended session is history and cannot be restarted or reuse its overlay URL. If a YouTube broadcast has ended or its chat is disabled, Stop the old session and create a new one using the currently active broadcast. This does **not** require reconnecting Google while `/settings/connections` still says connected. The interface gives plain-language recovery steps for common errors; technical error codes are secondary support details.

## Connect a real YouTube channel

Phase 2 reads live events only. It does not post chat messages or modify broadcasts.

1. Enable **YouTube Data API v3** in a Google Cloud project.
2. Create an OAuth client of type **Web application** and register this exact local redirect URI:

   `http://localhost:8000/api/v1/youtube/oauth/callback`

3. Generate an encryption key:

   ```powershell
   cd backend
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Set these backend-only values in `.env`:

   ```dotenv
   DATA_ENCRYPTION_KEY=generated-fernet-key
   GOOGLE_CLIENT_ID=your-web-client-id
   GOOGLE_CLIENT_SECRET=your-web-client-secret
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/youtube/oauth/callback
   YOUTUBE_SCOPES=https://www.googleapis.com/auth/youtube.readonly
   ```

5. Apply migrations, restart the backend, sign in, and open `/settings/connections`.
6. Connect Google, then open `/live`, choose **YouTube thật**, and select an active owned broadcast.

The worker prefers the official `liveChatMessages.streamList` gRPC API and resumes with its saved `nextPageToken`. If streaming is unavailable, it uses the official `list` API and obeys `pollingIntervalMillis`. The initial history is checkpointed but never spoken. See [docs/16_PHASE2_YOUTUBE_RUNBOOK.md](docs/16_PHASE2_YOUTUBE_RUNBOOK.md) for setup, error states, and the real-channel test checklist.

For chat testing, `YOUTUBE_CHAT_RESPONSE_MODE=all` (current default) lets Kira respond to every new, nonempty chat, including `Xin chào` without `Kira?`. This does **not** read old chat history or bypass duplicate, injection, Mute/Stop, streamer-first, paid-event priority, or the bounded 10-item/8-second chat queue. Rapid chat can still be dropped when that queue is full or stale. Real FPT/TTS replies can incur API usage. Set `YOUTUBE_CHAT_RESPONSE_MODE=addressed` in the backend environment and restart it to restore the quieter rule requiring Kira's name and `?`.

## Enable the real voice pipeline

Mock voice remains available. Voice Real requires server-side Deepgram plus the LLM and TTS selected in Character Studio. New characters default to FPT Marketplace `Saola-Small-32B` + gTTS; existing OpenAI characters retain OpenAI after migration:

1. Set `DEEPGRAM_API_KEY` for streaming Vietnamese STT. The default model is `nova-3-general`, language `vi`.
2. Set `FPT_API_KEY` in the backend-only `.env`, then select **FPT AI Marketplace** and `Saola-Small-32B`. The adapter uses the official `https://mkp-api.fptcloud.com/v1/chat/completions` streaming endpoint, Bearer authentication and provider-reported token usage. No key is sent to the browser. Alternatively, select **OpenAI** and set `OPENAI_API_KEY`; its existing Responses API adapter remains available with `store=false`.
3. For credential-free Vietnamese TTS, select **gTTS tiếng Việt**. It needs outbound internet but no Google Cloud credential. New characters default to gTTS.
4. Optional: select **Google Chirp 3 HD** after configuring its service-account JSON outside source control, or set `EDGE_TTS_EXPERIMENTAL_ENABLED=true` to expose the keyless but unsupported Edge endpoint.
5. Restart the backend, choose **Voice Real** when creating a live session, start the session, then click **Bật microphone**. Grant browser mic permission and use headphones.

The dashboard runs self-hosted Silero VAD in an AudioWorklet. It sends 16 kHz mono PCM16 only during detected speech through the authenticated short-lived-ticket WebSocket. Raw microphone audio is not persisted. Deepgram reconnects in place, and audio received while disconnected is dropped rather than replayed. Barge-in, mute, pause, and stop cancel the current LLM/TTS generation immediately. OBS remains the sole AI-audio owner, preventing duplicate playback on the dashboard.

Provider keys are backend-only. Never prefix them with `VITE_`, put them in overlay URLs, or paste them into the dashboard. gTTS and Edge are online third-party endpoints without API keys, not offline engines or guaranteed SLAs. For Docker, mount the optional Google credential file into the backend container and set the in-container absolute path. See [docs/17_PHASE3_VOICE_RUNBOOK.md](docs/17_PHASE3_VOICE_RUNBOOK.md) for setup and the real-provider verification checklist.

If an old `.env` has `DEEPGRAM_UTTERANCE_END_MS=900`, the adapter sends the hosted-service minimum of 1000 ms; update `.env` to 1000 to match `.env.example`. Without FPT credentials, Mock Mode still works and OpenAI can be selected when configured. FPT model availability and prices can change; the model allowlist and cost-rate variables are operator-configured, and missing rates are shown as unknown rather than zero.

To repeat the real-network provider checks (quota may be charged):

```powershell
cd backend
uv run python scripts/probe_deepgram.py
uv run python scripts/probe_real_voice_chain.py
uv run python scripts/benchmark_fpt_voice.py --repeats 2 --output-dir ../.tmp/fpt-voice-benchmark
```

The synthetic-speech chain does not exercise browser microphone, Silero VAD, WebSocket delivery or OBS. The FPT benchmark measures input text to first decoded gTTS PCM, not end-to-end audible latency. See [FPT_MARKETPLACE_VALIDATION_REPORT.md](FPT_MARKETPLACE_VALIDATION_REPORT.md).

Run the real-network free-TTS benchmark with:

```powershell
cd backend
uv run python scripts/benchmark_free_tts.py --repeats 2 --include-edge
```

The 2026-10-13 run measured gTTS at 10/10 successes, P50 333 ms and P95 441 ms to first decoded PCM. Experimental Edge reliability was 40% for Hoài My and 80% for Nam Minh, with much higher tail latency. Exported WAV files require human listening before claiming naturalness or pronunciation quality; see [FREE_TTS_VALIDATION_REPORT.md](FREE_TTS_VALIDATION_REPORT.md).

Before spending provider quota, open `/settings/diagnostics`. It shows a backend-only preflight (without keys, tokens, or credential paths), checks browser microphone support, performs an opt-in local mic-level test, loads metrics for a real session, calculates a 3-hour run-rate estimate after at least 60 seconds, and exports an operator evidence JSON. `PREFLIGHT_ONLY` is readiness information—not proof that any provider or OBS worked.

## Verify

```powershell
python harness/validate_pack.py
cd backend
uv run ruff check app tests
uv run mypy app
uv run ty check app
uv run python scripts/run_isolated_tests.py -q
cd ..\frontend
npm run lint
npm run build
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_isolated_playwright.ps1
```

Playwright's complete upstream suite needs Mailpit on ports 1025 and 8025. The focused live-character E2E test is `frontend/tests/live-character.spec.ts`.

The isolated backend test runner creates/migrates a separate `kira_voice_test` PostgreSQL database. Do not run plain `uv run pytest` against a development database containing characters or sessions: the upstream fixture historically deleted users at teardown, cascading into their data. The fixture now preserves rows that existed before a test run, but isolation remains the safe default. The PowerShell Playwright runner **replaces only the dedicated `kira_playwright_test` database** at the start of each run, then uses a test backend on `127.0.0.1:8001` and a test Vite frontend on `127.0.0.1:5174`. It leaves the development database/backend/frontend on ports `8000/5173` untouched; it refuses to drop the test database if another process is connected. Mailpit is still shared, so avoid concurrent email workflows while the full E2E suite runs.

If Docker Desktop is unavailable on Windows, run the official Mailpit binary directly with its default SMTP `1025` and HTTP `8025` listeners before Playwright. The final Phase 3 run used Mailpit `v1.31.4` with its published SHA-256 verified.

Manual OBS desktop verification is documented in [docs/15_MANUAL_OBS_TEST_GUIDE.md](docs/15_MANUAL_OBS_TEST_GUIDE.md). Automated Chromium checks cover transparency, audio ownership, exactly-once playback, talking/idle state, cancellation, and safe reconnect, but they are not a substitute for an OBS recording test.

Avatar setup verification (2026-10-14): backend **159/159**, focused Playwright **3/3**, frontend lint/build, Ruff, mypy, ty, and documentation harness passed. The full Playwright runner was not run because its reserved ports were occupied. Camera framing and zoom were saved and reloaded in Chromium; OBS still needs a safe backend restart after the currently ACTIVE preview session ends before those new settings are available to its live page. Exact details are in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

Latest local avatar verification (2026-10-14): backend Pytest **158 passed**, full isolated Playwright **75/75 passed** before the final reconnect-state UI adjustment, and the focused live-character suite **3/3 passed** after that adjustment. Lint, production build, type/security checks and the documentation harness passed. Arcana is local-only because its embedded license prohibits redistribution and commercial use; public/deployed builds use the procedural fallback until suitable rights are obtained. Real OBS verification is still pending. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for exact test provenance and [assets/LICENSE_REGISTER.md](assets/LICENSE_REGISTER.md) for model/animation terms.

If Start reports `Another live session is active`, open `/live` and return to that control room. Creating a draft does not replace a running session. If YouTube chat shows `chat_disabled_or_ended`, the video saved in that session may have ended: **Reconnect ingest only retries the same chat**. In **Chat của livestream YouTube → Đổi sang livestream đang phát**, choose an active broadcast from the connected channel, or paste its watch/share URL from YouTube Studio and click **Kiểm tra link**. Then confirm **Gắn chat của video này vào phiên**. The backend rechecks channel ownership, live status and active chat before switching only YouTube ingestion; mic and OBS URL stay in place. If there is no active broadcast, the video has ended, chat is unavailable, or the channel differs, correct that in YouTube Studio or Google Connections; the app will not guess a chat ID. Never paste stream keys or OAuth tokens—only the public video URL.

The Phase 1 stabilization baseline passed 78 backend tests and 63 Playwright tests. Phase 2 passed 95 backend tests and 64 Playwright tests. Phase 3 implementation passed 102 backend tests and 64 Playwright tests. The 2026-10-13 free-TTS extension passed 118 backend tests and 66 Playwright tests. The 2026-10-14 FPT integration passed 125 backend tests and 66 Playwright tests. The subsequent guided real-microphone attempt passed **126 isolated backend tests and 67 isolated Playwright tests**; its human/OBS results and unresolved checks are in [REAL_MIC_OBS_VALIDATION_REPORT.md](REAL_MIC_OBS_VALIDATION_REPORT.md). Earlier commands and external checks are recorded in [FPT_MARKETPLACE_VALIDATION_REPORT.md](FPT_MARKETPLACE_VALIDATION_REPORT.md), [FREE_TTS_VALIDATION_REPORT.md](FREE_TTS_VALIDATION_REPORT.md) and [PHASE3_REAL_WORLD_VALIDATION_REPORT.md](PHASE3_REAL_WORLD_VALIDATION_REPORT.md).

## Scope

- `MOCK_TESTED`: YouTube fixtures, director priorities, FakeLLM/FakeTTS, Silero integration build, binary audio protocol, simulated streaming/cancellation/reconnect behavior, usage accounting, and the local Arcana VRM overlay with procedural load-failure fallback (see current implementation status for exact test runs).
- `PREFLIGHT_TESTED`: provider configuration is reported without exposing secrets. The connected YouTube channel, broadcast discovery and chat receipt ingestion were subsequently exercised with real OAuth; the current evidence and limits are in `IMPLEMENTATION_STATUS.md`. Real Super Chat/Super Sticker delivery remains unverified.
- `REAL_PROVIDER_NETWORK_TESTED`: Deepgram streaming socket, one synthetic Vietnamese speech -> Deepgram -> FPT -> gTTS chain, and 10 FPT -> gTTS text turns. Timing is provider-side text/synthetic input to PCM, not audible OBS end-to-end.
- `REAL_TTS_NETWORK_TESTED`: separate keyless gTTS and experimental Edge synthesis, PCM decode, signal integrity, first-audio timing, reliability, and cancellation dispatch.
- `PARTIAL_REAL_MIC_OPERATOR_REPORTED`: browser microphone/VAD sent Vietnamese speech to Deepgram, three addressed turns reached FPT/gTTS and browser overlay playback ACK, and the operator saw a character in OBS and reported an affirmative audio response. Sample count is too small for reliable P50/P95; browser ACK is not OBS-audible latency. One proper name was recognized as “Pira”.
- `NOT_TESTED`: formal human-rated TTS quality and STT word-error rate, credentialed OpenAI/Google TTS, OBS-audible P50/P95, real Google consent/channel traffic, manual OBS recording/audio routing and individual barge-in/mute/stop/reconnect observations.
- Phase 4 has not been started.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), [PHASE3_REAL_WORLD_VALIDATION_REPORT.md](PHASE3_REAL_WORLD_VALIDATION_REPORT.md), [PHASE3_TEST_REPORT.md](PHASE3_TEST_REPORT.md), [docs/17_PHASE3_VOICE_RUNBOOK.md](docs/17_PHASE3_VOICE_RUNBOOK.md), [PHASE2_TEST_REPORT.md](PHASE2_TEST_REPORT.md), and [UPSTREAM_TEMPLATE_README.md](UPSTREAM_TEMPLATE_README.md) for details.
