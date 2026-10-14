# Phase 3 real voice runbook

Status: implementation and automated Mock validation complete. Deepgram + FPT + gTTS real-network checks used synthetic speech; browser microphone, OBS, Google TTS and real YouTube traffic remain pending.

## Supported path

`browser mic -> self-hosted Silero VAD -> authenticated dashboard WebSocket -> Pipecat Deepgram stream -> Conversation Director -> selected FPT Chat Completions or OpenAI Responses stream -> selected TTS adapter -> PCM16 binary WebSocket -> OBS overlay Web Audio`

Mock voice and the Phase 2 YouTube event source remain independently selectable. The application does not install or run LiveKit Agents.

## Provider configuration

Use `.env.example` as the key list. Required backend-only values are:

```dotenv
DEEPGRAM_API_KEY=...
DEEPGRAM_MODEL=nova-3-general
DEEPGRAM_LANGUAGE=vi
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
FPT_API_KEY=...
FPT_LLM_MODEL=Saola-Small-32B
DEFAULT_REAL_LLM_PROVIDER=fpt
DEEPGRAM_UTTERANCE_END_MS=1000
DEFAULT_REAL_TTS_PROVIDER=gtts
# Only when the character selects Google Chirp:
GOOGLE_APPLICATION_CREDENTIALS=C:/secure/google-tts-service-account.json
GOOGLE_TTS_VOICE_ID=vi-VN-Chirp3-HD-Leda
# Optional, unsupported endpoint:
EDGE_TTS_EXPERIMENTAL_ENABLED=false
EDGE_TTS_VOICE_ID=vi-VN-HoaiMyNeural
```

Select the LLM provider/model and TTS provider/voice in Character Studio. FPT is the default for new characters; existing characters retain OpenAI after the migration. FPT and OpenAI keys stay server-side and are only required for the selected provider. gTTS needs no credential but does require outbound internet. The optional Google path must be visible inside the backend process/container; never store its JSON in this repository. Edge TTS uses an unofficial online endpoint and remains disabled by default. Optional per-provider cost-rate variables are deliberately blank because vendor prices change. Free-provider TTS cost is zero in the estimator; STT and selected LLM rates are still required for a complete estimate.

Current API/model choices were rechecked on 2026-10-13 against official documentation:

- [Deepgram models and languages](https://developers.deepgram.com/docs/models-languages-overview/) and [streaming STT reference](https://developers.deepgram.com/reference/speech-to-text/listen-streaming): Nova-3 general, Vietnamese `vi`, linear16 streaming, interim/final results and endpointing.
- [FPT Marketplace integration](https://github.com/fpt-corp/ai-marketplace/blob/main/API%20Integration%20-%20Large%20Language%20Model.md) and [serverless inference API](https://docs.fptcloud.com/docs/fpt-ai-factory/services/serverless-inference/tutorials/call-the-api/): `POST https://mkp-api.fptcloud.com/v1/chat/completions`, Bearer key, streaming `choices[].delta.content` and terminal usage. The live `/v1/models` catalog listed `Saola-Small-32B` on 2026-10-14; recheck model access and pricing on your account before production.
- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and [Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses): environment-configurable `gpt-5.4-mini`, streaming text deltas, and final usage. The former `gpt-5-mini` default is deprecated. Requests use `store=false`.
- [Google Chirp 3 HD](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd) and [voice list](https://cloud.google.com/text-to-speech/docs/voices): Vietnamese `vi-VN`, Chirp 3 HD voice names and streaming PCM.
- [gTTS 2.5.4](https://pypi.org/project/gTTS/) writes Google Translate TTS MP3 without an API key. It is not an official Google Cloud API or offline engine.
- [edge-tts](https://github.com/rany2/edge-tts) uses the Microsoft Edge online speech service without an API key. Version 7.2.8 is pinned because 7.3.0 returned no audio in local validation; the endpoint has no product SLA for this use.

## Browser and audio behavior

- Serve the dashboard from HTTPS outside localhost; browsers require a secure context for microphone capture.
- Click **Bật microphone** after the session is active. Audio constraints request mono, echo cancellation, noise suppression, and automatic gain control.
- Use headphones. The dashboard never plays AI speech; the overlay is the sole output.
- Silero VAD sends a roughly 192 ms pre-roll, triggers barge-in on speech start, and finalizes rapidly after speech end.
- Binary frames are versioned and bounded. Malformed, wrong-direction, oversized, out-of-order, duplicate, or wrong-turn frames are rejected/dropped.
- No raw microphone audio is written to the database, logs, trace payloads, or files. Short context memory is bounded and process-local.

## Failure/reconnect behavior

- Pipecat maintains the Deepgram WebSocket and keepalive/reconnect lifecycle.
- Mic frames arriving while STT is disconnected are counted and dropped; they are never replayed after reconnect.
- The selected FPT/OpenAI LLM retries once only if it has emitted no text. It then uses a clearly reported local text fallback; cancellation closes the provider stream.
- Any selected TTS failure uses generated local PCM and emits `provider.health=degraded_fallback`; fallback latency is excluded from provider performance.
- Mute, pause, stop, and streamer barge-in increment the generation and cancel active provider tasks. The overlay stops all scheduled sources and acknowledges cancellation.
- Overlay reconnect receives state only. Speech audio is excluded from replay history.

## Metrics

The session usage endpoint reports STT seconds, LLM input/output tokens, TTS characters, provider errors, reconnect episodes, dropped mic frames, optional estimated cost, and P50/P95 timing summaries. Timings include `stt_final_ms` (server receipt of browser VAD end to final transcript), event-to-decision, LLM first token/complete, TTS first audio, server-to-overlay playback ACK, `voice_end_to_first_playback_ack_ms`, and cancellation dispatch/ACK.

The usage response also includes `observed_session_seconds`, `usage_measurement_scope`, and `projected_3h_usd`. The three-hour figure appears only for Voice Real after at least 60 seconds and when every operator-supplied rate is configured. It is `observed estimated cost * 10800 / observed seconds`, so it is a run-rate estimate, not an invoice.

`usage_basis` makes counter provenance explicit: STT seconds are PCM frames accepted by the STT pipeline, LLM tokens come from completed provider responses, TTS characters are text submitted to the TTS pipeline, and USD is calculated from operator rates rather than provider billing exports.

Measurement scopes are explicit:

- `MOCK_SIMULATED_LOCAL`: FakeLLM/FakeTTS.
- `SIMULATED_PROVIDER_LOCAL`: benchmark adapters; no network/provider/OBS.
- `REAL_PROVIDER_LOCAL`: emitted only for a real-voice session. It is meaningful only when provider health confirms real connections and an overlay supplies playback ACKs.
- `DEGRADED_FALLBACK_LOCAL`: a trace used local fallback text or PCM. Its end-to-end timing is retained on the trace but excluded from real-provider P50/P95.

## Guided diagnostics

1. Sign in and open `/settings/diagnostics`.
2. Fix every backend provider marked **Chưa sẵn sàng**. A Google credential reference is invalid unless the backend can read the file.
3. Click **Kiểm tra microphone cục bộ**, speak for one second, and confirm a non-zero peak. The page stops the track and does not upload or persist audio.
4. Create a **Voice Real** session from `/live`, start it, open the unique overlay URL in OBS, and run for at least 60 seconds.
5. Paste the session UUID into diagnostics to inspect STT/LLM/TTS usage, P50/P95, errors, reconnects, and the optional 3-hour cost projection.
6. Complete each manual Vietnamese/OBS checkbox, then export the JSON. Checkboxes are explicitly operator-recorded evidence and never count as automated PASS.

## Credential-free TTS benchmark

Run `uv run python scripts/benchmark_free_tts.py --repeats 2 --include-edge` from `backend/`. It makes real network calls and writes one WAV per voice plus `benchmark.json` under `.tmp/free-tts-benchmark` by default.

The 2026-10-13 run used five Vietnamese prompt categories with two repetitions. gTTS passed 10/10 with first decoded PCM P50 332.978 ms and P95 440.630 ms. Edge Hoài My passed 4/10 (P50 3538.569 ms, P95 6301.706 ms); Edge Nam Minh passed 8/10 (P50 3620.961 ms, P95 13846.639 ms). Successful audio had non-silent, non-clipping PCM signal integrity. Naturalness, pronunciation, and gaming-slang quality remain `NOT_TESTED` until a human listens to the WAV files.

Suggested spoken set:

- Neutral Vietnamese: `Kira, tóm tắt tình huống trận này trong hai câu.`
- Gaming slang: `Kira, combat này team mình outplay hay feed vậy?`
- Mixed terms: `Kira, check cooldown ulti rồi call team push mid nhé.`
- Persona: ask the same question three ways; verify name, pronouns, humor level, and forbidden behavior remain consistent.
- Feedback challenge: play game audio through the normal output, speak through a headset mic, and count false barge-ins. VAD is not speaker identification.

## Real-provider acceptance checklist (pending)

1. Use a non-production test account/project with billing caps and all three credentials.
2. Confirm the browser Network panel never receives provider credentials.
3. Speak Vietnamese turns with and without saying the character name; only directly addressed final transcripts should respond.
4. Interrupt speech, then test Mute and Stop. Verify no later PCM chunk plays and cancellation ACK latency is recorded.
5. Disconnect/reconnect the dashboard and overlay. Verify no old audio replays.
6. Exercise a queued Super Chat while the streamer is speaking.
7. Record at least 30 turns and report `stt_final_ms`, LLM first token, TTS first audio, and `voice_end_to_first_playback_ack_ms` P50/P95 with device, browser, region, and network.
8. Complete [the manual OBS guide](15_MANUAL_OBS_TEST_GUIDE.md), including transparent background and audio monitoring/routing.

Do not mark this checklist passed from simulated adapters.

If **Bật microphone** reports `no available backend found` and a failed
`/vad/ort-wasm-simd-threaded.mjs?import` fetch in local Vite development, check
that the URL returns JavaScript with HTTP 200. The development server serves this
self-hosted ONNX module through an exact-path Vite middleware; the WASM and model
must also return HTTP 200. After restoring asset delivery, hard-refresh the
control room before retrying because ONNX caches a failed `initWasm()` in the
current page. A successful synthetic browser VAD initialization is not proof of
physical microphone detection or OBS playback.
