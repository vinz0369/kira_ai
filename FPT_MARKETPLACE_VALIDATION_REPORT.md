# FPT Marketplace + Deepgram + gTTS validation — 2026-10-14

## Scope and outcome

The new FPT Chat Completions adapter is selectable per character. Mock, OpenAI and all TTS choices remain available. The provider path was tested with real FPT, Deepgram and gTTS network calls. Browser microphone, Silero VAD, real OBS audio routing, YouTube channel traffic and human listening were **not** exercised. Phase 4 was not started.

The official [FPT integration guide](https://github.com/fpt-corp/ai-marketplace/blob/main/API%20Integration%20-%20Large%20Language%20Model.md) and [FPT API tutorial](https://docs.fptcloud.com/docs/fpt-ai-factory/services/serverless-inference/tutorials/call-the-api/) were checked before coding. The authenticated catalog returned `Saola-Small-32B`; the adapter used `POST https://mkp-api.fptcloud.com/v1/chat/completions`, Bearer authentication, streaming text deltas and terminal usage. No provider key is printed by the benchmark or sent to the frontend.

## Real-network measurements

Command: `cd backend; uv run python scripts/benchmark_fpt_voice.py --repeats 2 --output-dir ../.tmp/fpt-voice-benchmark`. This sent five short Vietnamese/gaming prompts twice through FPT -> gTTS. All 10 attempts produced FPT text and decoded PCM without fallback. The JSON evidence and one WAV sample are under `.tmp/fpt-voice-benchmark/` (local, not committed).

| Metric | Result | Meaning |
|---|---:|---|
| FPT first text token P50 / P95 | 190.469 / 334.681 ms | From submitted text to first LLM delta |
| First decoded gTTS PCM P50 / P95 | 728.682 / 1112.090 ms | From submitted text, **not** end-of-mic-turn or OBS playback |
| Reliability | 10/10 | This small network sample only |
| FPT usage | 686 input + 173 output tokens | Provider-reported completed-response usage |
| FPT LLM cost estimate | USD 0.00011513 total | Tokens x prices returned by live `/v1/models` catalog; not an invoice |
| Cancel dispatch to stopped task | 0.694 ms | Local task cancellation after first PCM; no extra chunk after 100 ms wait |

Mean measured FPT LLM cost was about USD 0.0000115/turn for these short prompts. At an **assumed** 10 comparable turns/minute for three hours, that would extrapolate to about USD 0.0207 for FPT text only. Real livestream prompts, context length, price changes, Deepgram charges, network behavior and billing can alter this substantially; this is not a measured three-hour bill. Session cost estimates remain unavailable until current operator rates are set in `.env`.

Command: `cd backend; uv run python scripts/probe_deepgram.py` connected to the real Deepgram Vietnamese streaming WebSocket at 16 kHz. A separate `scripts/probe_real_voice_chain.py` run synthesized one Vietnamese prompt in memory, sent PCM through the Pipecat Deepgram stream, then passed the transcript to FPT and gTTS. It returned a transcript, a Vietnamese answer and 19 PCM chunks without fallback. Synthetic speech-end to STT final was 1098.343 ms; FPT first token 337.265 ms; gTTS first audio 398.873 ms. The input was gTTS-generated speech, **not** a person speaking into browser mic. Deepgram imperfectly transcribed the name “Kira”; a human speech/slang accuracy test remains necessary.

The Deepgram live connection initially failed HTTP 400. Isolation of the actual connect query showed two causes: Pipecat connected before its setup frame and sent `sample_rate=0`, and the old default `utterance_end_ms=900` was rejected by Deepgram hosted streaming. Initializing the service to 16 kHz and clamping the old value to 1000 resolved the live connection. Deepgram's [endpointing guide](https://developers.deepgram.com/docs/endpointing/) uses 1000 ms for UtteranceEnd.

Vietnamese output was produced for all benchmark prompts, including short gaming requests and an untrusted viewer instruction. This verifies text generation, **not** natural voice quality, personality over a long stream, or prompt-injection resistance in the wild. WAV listening and a 10–15 minute human mic session remain pending.

## Regression and security checks

Executed locally:

| Command | Result |
|---|---|
| `uv run alembic current` | `ea2f6a419c04 (head)`; migration downgrade/upgrade also completed during implementation |
| `uv lock --check` | PASS, 152 packages resolved |
| `uv run ruff check app tests scripts/benchmark_fpt_voice.py scripts/probe_deepgram.py scripts/probe_real_voice_chain.py` | PASS |
| `uv run mypy app` | PASS, 49 files |
| `uv run ty check app` | PASS |
| `uv run pytest -q` | PASS, 125 tests, 78 warnings |
| `npx -y bun@1.3.12 run lint` | PASS, 89 files; formatter fixed 2 files |
| `npx -y bun@1.3.12 run build` | PASS, TypeScript and Vite; existing large lazy 3D chunk warning |
| `python harness/validate_pack.py` | PASS, 6 skills and 8 fixtures; docs validation only |
| `npx -y bun@1.3.12 audit` | PASS, no vulnerabilities |
| `uvx pip-audit --path ..\\.venv\\Lib\\site-packages` | No known vulnerabilities; local `app` is not on PyPI and was skipped |
| `npx -y bun@1.3.12 x playwright test --project=chromium --reporter=line --workers=2` | PASS, 66/66 in 2.0 minutes after fixture reset and YouTube-state assertion fix |
| Exact-value scan of built frontend for configured provider secrets | PASS, 2 nonempty provider secrets checked, 0 matches |

Playwright's first run stopped in auth setup because backend Pytest had removed the test superuser from the shared local database. Running `uv run python app/initial_data.py` restored the expected fixture. The next run reached 65/66; its YouTube UI test assumed no OAuth client credentials, while this `.env` has credentials but no connected channel. The test was changed to assert either truthful `not_configured` or `disconnected` UI, while still rejecting a false connected state. A full suite was then rerun without skipping tests.

The local development `SECRET_KEY`, database password and superuser password remain template-strength examples (`changethis`); replace them before any public deployment. OpenAI and Google TTS were preserved and covered by automated tests but were not called live in this run. Real YouTube OAuth consent and broadcast ingestion were not tested. OBS Studio was not opened, so browser-source transparency, audio mixer routing and audible P50/P95 remain **pending**; follow `docs/15_MANUAL_OBS_TEST_GUIDE.md` and `docs/17_PHASE3_VOICE_RUNBOOK.md`.
