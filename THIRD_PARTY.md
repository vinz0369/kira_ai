# Third-party code register

Pinned by the lockfiles. Media assets are tracked separately in `assets/LICENSE_REGISTER.md`.

| Package / project | Version / commit | License | Use |
|---|---:|---|---|
| FastAPI Full Stack Template | `7257e606cb94eada1dca40173e2b7f99dd549bc6` | MIT | Base React/Vite, FastAPI, auth, SQLModel, Alembic, Docker, CI, Playwright/Pytest |
| `@react-three/fiber` | 9.8.1 | MIT | React renderer for the overlay scene |
| `@react-three/drei` | 10.7.9 | MIT | Lightweight scene helpers |
| `@pixiv/three-vrm` | 3.5.5 | MIT | VRM loader and expression integration; no model asset bundled |
| `three` | 0.186.1 | MIT | 3D runtime used through React Three Fiber |
| Redis | 8.2 Alpine image | RSALv2 / SSPLv1 / AGPLv3 tri-license; verify deployment choice | Phase 0 local ephemeral service; Phase 1 process-local runtime remains explicit |
| `google-api-python-client` | 2.201.0 | Apache-2.0 | Official YouTube Data API discovery client for channels, broadcasts, and polling fallback |
| `google-auth-oauthlib` | 1.5.0 | Apache-2.0 | Google OAuth web-server authorization code flow with state and PKCE |
| `grpcio` | 1.84.0 | Apache-2.0 | Official YouTube `liveChatMessages.streamList` transport |
| `protobuf` | 6.33.6 | BSD-3-Clause | YouTube streaming message serialization |
| `cryptography` | 50.0.2 | Apache-2.0 / BSD-3-Clause | Fernet encryption for OAuth tokens and PKCE verifier at rest |
| YouTube `stream_list.proto` schema subset | Docs updated 2026-09-14 | Apache-2.0 sample code | Wire-compatible generated bindings; original field numbers preserved |
| Pipecat AI | 1.12.0 | BSD-2-Clause | Streaming service lifecycle and Deepgram STT reconnect orchestration; LiveKit Agents is not installed |
| `@ricky0123/vad-web` | 0.0.31 | ISC | Browser microphone Silero VAD and AudioWorklet integration |
| Silero VAD v5 model | bundled by `@ricky0123/vad-web` 0.0.31 | MIT | Self-hosted ONNX voice-activity model; no microphone audio leaves the browser while idle |
| `onnxruntime-web` | lockfile version | MIT | Local WebAssembly inference runtime for Silero VAD |
| Deepgram Python SDK | 7.13.0 | MIT | Official streaming transport used through Pipecat (`nova-3-general`, Vietnamese) |
| OpenAI Python SDK | 3.29.0 | Apache-2.0 | Responses API streaming LLM adapter; model ID is environment-configured |
| Google Cloud Text-to-Speech | 2.38.0 | Apache-2.0 | Chirp 3 HD bidirectional streaming TTS adapter |
| `gTTS` | 2.5.4 | MIT | Credential-free Vietnamese TTS through the online Google Translate speech endpoint; not an official Google Cloud API |
| `edge-tts` | 7.2.8 | LGPL-3.0 | Optional experimental Vietnamese TTS through the online Microsoft Edge speech endpoint; 7.3.0 was excluded after a zero-audio regression in local validation |
| PyAV (`av`) | 16.1.0 | BSD-3-Clause | In-memory MP3 decode and resample to the overlay PCM16 contract; no TTS audio is persisted by the runtime |

See each dependency's installed package metadata and upstream LICENSE before redistribution. Dependency code licenses never grant rights to unrelated demo avatars or recordings.
