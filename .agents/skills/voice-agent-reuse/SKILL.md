---
name: voice-agent-reuse
description: Prototype Pipecat-based streaming STT LLM TTS and interruption for browser-microphone to OBS-overlay audio, with low latency and provider adapters.
---
# Voice runtime reuse / Pipecat spike

Read `docs/06_VOICE_LATENCY.md`, `docs/11_GITHUB_REUSE_MATRIX.md`, `docs/14_TEMPLATE_MIGRATION_ADR.md` and recent Pipecat SDK docs.

## Procedure

1. Avoid code until Phase 1 mock can send synthetic voice transcripts and play cancelable audio in OBS overlay.
2. Browser VAD from `@ricky0123/vad-web` (not raw desktop/OBS audio). Keep `AudioWorklet` minimal. VAD doesn't label the speaker.
3. Evaluate Pipecat adapters/processors and suitable transport; verify dual client topology (dashboard mic input, separate OBS browser output) actually works.
4. Use streaming STT partial/final and bounded turn-end detection. Feed only eligible candidates to Director; no LLM on every token.
5. Generate chunked TTS, track first-audible latency with overlay ACK. Implement idempotent cancellation/barge-in; handle task abort/reconnect/expired replies.
6. Measure P50/P95 on Vietnamese+gaming utterance set; log STT seconds, token and TTS usage, no raw audio at rest.
7. If Pipecat cannot meet topology, latency or deployment constraints, record measured ADR before switching to LiveKit Agents; never install both in prod.

## Done when

A real headset/mic session runs end-to-end with interruption and bounded queue, plus mock/offline tests; benchmark records **actual** first-audible latency, not provider estimates.
