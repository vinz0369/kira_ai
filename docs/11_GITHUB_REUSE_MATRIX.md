# 11 — GitHub reuse matrix: reuse trước, tự viết sau

**Đã rà soát ngày 2026-10-12.** Star count là **xấp xỉ tại ngày kiểm tra**, không phải quality guarantee hay license của assets. Pin version/commit và kiểm tra changelog/security advisory tại thời điểm Codex cài. Repo ở đây là **dependency hoặc template** chứ không phải tính năng đã chạy trong project. **Không copy toàn bộ source 3D/voice framework vào repo ứng dụng.**

## Matrix ưu tiên

| Vai trò | Repo, URL, stars ~ | License code | Quyết định / Reuse thực tế |
|---|---|---|---|
| **App scaffold** | https://github.com/fastapi/full-stack-fastapi-template — **45.9k** | MIT | **ADOPT BASE**: `frontend/` React+Vite, FastAPI backend, SQLModel, Postgres, Docker, auth, GitHub Actions, Playwright, pytest. Tạo repo qua **Use this template**; không build login/user management/CI từ đầu. |
| Voice framework | https://github.com/pipecat-ai/pipecat — **15.6k** | BSD-2-Clause | **PREFERRED SPIKE (Phase 3)**: inspect built-in pipeline, transports, interruption, VAD, STT/LLM/TTS integrations. Avoid writing own general voice runtime. Verify browser → server + server → **separate OBS overlay** bridge before adopting. |
| Alternate voice | https://github.com/livekit/agents — **14.2k** | Apache-2.0 for framework; **separate LiveKit model license** | **FALLBACK ONLY** if Pipecat spike can't meet deployment/cost/latency/bridge needs. May need LiveKit server/Cloud. Never run both. |
| Browser VAD | https://github.com/ricky0123/vad — **2.1k** | ISC for wrapper; Silero ONNX model MIT in repo | **ADOPT** `@ricky0123/vad-web`, only if works with target Chromium/CEF. VAD ≠ speaker diarization; not guarantee removal of game audio from mic. |
| React 3D renderer | https://github.com/pmndrs/react-three-fiber — **32.9k** | MIT | **ADOPT** `@react-three/fiber`, avoid bespoke Three.js canvas lifecycle inside React. |
| React 3D helpers | https://github.com/pmndrs/drei — **9.9k** | MIT | **ADOPT** only used helpers. No heavyweight game engine. |
| VRM format | https://github.com/pixiv/three-vrm — **2.2k** | MIT | **ADOPT** `@pixiv/three-vrm` for VRM loader/expressions/blendshapes. **Code license not asset license.** |
| Talking avatar alternative | https://github.com/met4citizen/TalkingHead — **1.6k** | MIT code | **REFERENCE / optional spike** only. Primarily GLB with compatibility/rig requirements, demo assets may be **noncommercial**. Do not import the examples as commercial models. |
| Google Node SDK | https://github.com/googleapis/google-api-nodejs-client — **12.3k** | Apache-2.0 | **REFERENCE only** for official API strategy. Backend Python must use Google's **official Python client**, not install this Node SDK in Python backend. |
| Web E2E | https://github.com/microsoft/playwright — **96.3k** | Apache-2.0 | **Already in base**; extend current tests, especially overlay and mute. |
| Frontend unit | https://github.com/vitest-dev/vitest — **17.2k** | MIT | Add only if upstream lacks unit testing for Director/frontend helpers; keep existing tooling wherever present. |
| Voice example patterns | https://github.com/pipecat-ai/pipecat-examples — **~395** | BSD-2-Clause | Lower-stars examples from **same maintainers** are useful for real SDK usage; choose smallest voice workflow matching browsers, no blind copy. |

## Immediate reuse boundary

**Reuse almost intact:** template auth, database migrations, UI component system, Docker Compose, lint/test pipelines, existing FastAPI routes and generated API client.

**Reuse as dependency:** VAD, Three-VRM, R3F/Drei; Pipecat after viability test; provider SDKs only in adapters.

**Our product-specific code:** transcript/chat/superchat input normalization, decision priorities and expiry, streamer-first turn-taking, character persona/memory, event bridge to OBS overlay, playback ACK, billing/usage safeguards, YouTube OAuth authorization and event mapping.

## Critical caveats — do not conflate repo popularity with drop-in compatibility

1. **Pipecat is not an OBS/browser overlay product**. Need a tiny integration layer to fan out generated audio and expression events to a separate OBS Browser Source, and receive ACK. Conduct a working 30–60 min prototype with fake provider before locking in. Decide in ADR whether to use its transport end-to-end or integrate as processor-only; don't build two concurrent audio buffering/turn-end systems.
2. **LiveKit Agents** typically uses LiveKit room/infrastructure; highly capable but not necessarily simplest if we only need dashboard mic + OBS output. Check hosting costs and interop.
3. **TalkingHead** expects particular GLB morph targets/visemes; VRM isn't automatically plug-and-play; demo avatars have separate licenses. Our primary plan is `three-vrm` with audio amplitude mouth animation for MVP.
4. `full-stack-fastapi-template` uses Vite+React rather than Next.js, and includes JWT auth; **reuse it rather than migrating all scaffolding to Next.js or building duplicate login**. User's product requirement was Web App, not SEO/SSR.
5. `ricky0123/vad` recognizes speech activity, not who is speaking. Direct mic + headphones matter more than expensive source separation for Phase 3.
6. An asset on GitHub may be under different rules than its repository. Any VRM/animation/voice asset to ship must have verified **commercial redistribution** rights, attribution requirements, and source logged in `assets/LICENSE_REGISTER.md`.
7. YouTube `liveChatMessages.streamList` is official; inspect live API client support in Python/version and fallback `list` per polling interval. **Don't build a bot that scrapes YouTube DOM**.

## Integration decision tree (Codex)

- Need scaffold UI/auth/DB/CI? **Use existing template code.**
- Need low-latency continuous STT+LLM+TTS with interruption? **Spike Pipecat**, integrate per adapter interfaces; only fallback LiveKit when measurable issue.
- Need VRM character animation? **R3F+Drei+Three-VRM**, generic procedural 3D avatar until asset license cleared.
- Need YouTube events? **Use Python Google API client or official HTTP endpoint** and own mapper; do not use unofficial platform scraping.
- Need tests? **Extend template pytest/Playwright** plus provided fixtures; no new custom test runner.

## Licence & provenance process

1. Before adopting, capture upstream URL, LICENSE path, tag/commit SHA, dependency version, notices, update date in `THIRD_PARTY.md` (create when code is added).
2. Pin dependencies; `npm audit`/`pip audit` or equivalents; distinguish critical and noncritical.
3. For non-code media, confirm rights for display **and redistribution in publicly accessible web bundle**.
4. No bundling the third-party repositories/VRM models in this documentation ZIP; Codex installs libraries at build time using official package registries.

## Sources / audit links

- https://github.com/fastapi/full-stack-fastapi-template
- https://github.com/pipecat-ai/pipecat/blob/main/LICENSE
- https://github.com/livekit/agents
- https://github.com/ricky0123/vad/blob/master/LICENSE
- https://github.com/pixiv/three-vrm/blob/dev/LICENSE
- https://github.com/met4citizen/TalkingHead/blob/main/LICENSE
- https://github.com/met4citizen/TalkingHead (demo model license details)
- https://github.com/microsoft/playwright
- https://github.com/googleapis/google-api-nodejs-client
