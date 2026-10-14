# ADR-001 — Reuse FastAPI Full Stack Template; frontend Vite instead of Next.js

- Status: **ACCEPTED FOR CODEX MVP BUILD PACK v2**
- Date: 2026-10-12
- Source: https://github.com/fastapi/full-stack-fastapi-template
- Context: User yêu cầu không tự build lại những hệ thống OSS có hàng chục nghìn stars. v1 spec từng chọn Next.js và FastAPI do kiến trúc gợi ý, **không phải nhu cầu sản phẩm bắt buộc**. Product là dashboard + overlay Browser Source, không cần SSR/SEO.

## Decision

Use **upstream FastAPI Full Stack Template** as scaffold, retaining **React+Vite/TanStack Router/Query, shadcn/ui, FastAPI, SQLModel/PostgreSQL, auth, Docker, existing Playwright/Pytest/CI**. New features in `frontend/` and `backend/`, not parallel `apps/web` / `apps/api`.

### Existing template authentication versus v1 cookie-based contracts

- **Reuse upstream user auth**. Do not create duplicate login/password storage.
- **YouTube Google OAuth** is added as an **account integration** after user authenticates. YouTube permissions are separate from login.
- For browser Dashboard WebSocket, authenticated user obtains **short-lived, single-use WS ticket** from backend REST; WS validates ticket + origin + session owner. Do not expose long-lived JWT/OAuth refresh token in query params.
- For OBS overlay, use scoped, revocable **read-only capability token** in overlay URL (only when required); scrub URLs from logs, analytics, referrers; rotate/revoke, prevent write/control commands and unauthorized session enumeration.
- Adjust `/api/v1/me` v1 reference to existing upstream current user endpoint (typically `/api/v1/users/me`; verify source before changing). Add routes under existing API router without duplicating upstream endpoints.
- If using cookies for auth at some point, add CSRF; if using bearer stored in browser, apply XSS hardening and token refresh safeguards. Document whichever implementation tests confirm.

### Reasons not to force Next.js

1. Changing template to Next.js would discard/scramble upstream frontend routing, auth, generated client, tests and CI — cost contradicts reuse objective.
2. OBS overlay is static browser UI driven by WebSocket; Vite works well.
3. Faster Phase 0 onboarding/testing means focus on Conversation Director and voice latency.

### Consequences and verification

- `docs/00`, `02`, `04`, `07`, `10`, README and AGENTS updated to match decision.
- Review actual template commit before coding; its API/paths can evolve. Pin version.
- If user later requires SSR/Next-specific capability, reconsider with a new ADR, not an unnoticed migration.

## ADR-002 (pending) — Pipecat vs LiveKit

- Candidate: Pipecat 15.6k stars, BSD-2-Clause, composable voice pipeline and WebRTC/WebSocket transports.
- Alternative: LiveKit Agents 14.2k stars, Apache-2.0 framework, separate model license and possible LiveKit infra.
- Required test: browser mic → low-cost VAD/STT → LLM → streaming TTS → **different OBS overlay client**, barge-in, cancel, reconnect; benchmark latency, resource and code volume.
- Decision only after executable proof in Phase 3; **do not install both simultaneously**.
