# Codex project instructions — AI Live Character (v2)

## Thứ tự nguồn chân lý

1. `AGENTS.md` (file này) và `docs/14_TEMPLATE_MIGRATION_ADR.md` cho quyết định dùng template/Vite.
2. `docs/00_BUILD_ORDER.md` và `docs/11_GITHUB_REUSE_MATRIX.md` cho thứ tự và reuse.
3. `docs/04_API_EVENT_CONTRACTS.md`, `docs/05_CONVERSATION_DIRECTOR.md`, `docs/06_VOICE_LATENCY.md` cho behavior/transport.
4. Existing **FastAPI full-stack template code**, pinned dependency versions, official vendor docs cho API có thể đổi.
5. Skills trong `.agents/skills/` khi nhiệm vụ phù hợp. Nếu xung đột, ưu tiên file gốc + ADR.

## Không được làm

- Không scaffold Next.js, không viết framework auth/CRUD/test runner/3D renderer/voice orchestration từ đầu khi upstream có sẵn; không thay template bằng boilerplate ngẫu nhiên.
- Không cài hoặc chạy cả Pipecat lẫn LiveKit Agents trong một MVP: **Pipecat là ứng viên đầu**, thay thế chỉ sau spike có kết quả ghi lại.
- Không fake UI là thật: `MOCK_MODE=true` phải có badge Mock; mock provider phát audio demo thực (tự tạo hoặc có giấy phép) để thử overlay.
- Không API keys, OAuth secrets, credentials, audio raw, long-lived overlay token trong code, source control, client log, trace hoặc URL đo analytics.
- Không auto-điều khiển OBS/cảnh, screenshot, TikTok, nhắn chat YouTube; không thương mại hóa model VRM chưa kiểm tra license.
- Không xóa/viết lại auth, Docker CI và E2E có sẵn của template chỉ để cấu trúc giống docs v1.
- Không claim đạt hiệu năng voice/OBS/YouTube khi mới có mock; không claim 'tested' nếu chưa thực thi.

## Quyết định và kiến trúc bắt buộc

- Base repo https://github.com/fastapi/full-stack-fastapi-template; **React+Vite `frontend/`**, **FastAPI `backend/`** theo scaffold upstream; PostgreSQL, SQLModel, Alembic, Docker, existing Playwright/Pytest; bổ sung Redis ở nơi phù hợp.
- User authentication tái sử dụng template; **YouTube OAuth** là integration riêng và token Google phải lưu encrypted. Không làm lại toàn bộ auth cho bằng cách dùng cookie mô tả ở v1; thực hiện WS short-lived ticket cấp từ authenticated API theo ADR.
- 3D: `@react-three/fiber`, `@react-three/drei`, `@pixiv/three-vrm`; animated fallback procedural nếu chưa có model có quyền phân phối; **không lấy bừa model demo**.
- Browser micro → browser VAD → STT backend/voice runtime, không capture mixed OBS desktop audio; Dashboard thu mic, overlay OBS phát AI **duy nhất một nơi**.
- Event contract `docs/04_API_EVENT_CONTRACTS.md`, priority streamer control P0 > direct voice P1 > paid events P2 > optional interaction P3; chat/donate luôn untrusted.
- Every utterance cancellable and stamped generation/TTL; barge-in may interrupt, mute/stop is immediate control-plane action independent of LLM.
- STT/LLM/TTS via provider adapters + fake adapters, model/voice IDs env; no hard-code cost or vendor SDK into director.
- Privacy: no raw mic persistence by default; long-term memories opt-in/review/delete; strict overlay scope, CSRF/origin/security checks.

## Quy trình mỗi Codex task

1. `git status`, đọc files liên quan; xác nhận đây là source template hay docs-only.
2. Chọn skill task thích hợp (`.agents/skills/*/SKILL.md`), chỉ đọc tài liệu cần cho task; reuse upstream trước khi viết mới.
3. Triển khai **một vertical slice** trong Phase 0/1 trước; không làm hết roadmap một lượt.
4. Viết tests cho behavior, integration/failure/reconnect; fixture trong `harness/scenarios/` phải được chuyển thành executable tests.
5. Chạy checks hiện hữu trong template và `python harness/validate_pack.py`. Ghi lệnh/kết quả thực tế trong `IMPLEMENTATION_STATUS.md`.
6. Nếu thay đổi behavior, cập nhật docs/contracts/tests cùng lúc. Nếu thay thế repo/library, lập ADR có benchmark/license.

## Acceptance gates (không đánh dấu PASS nếu chưa chạy)

- **Docs gate:** `python harness/validate_pack.py` pass.
- **Scaffold gate:** dev server frontend/backend chạy; database migrations và health; lint/typecheck/pytest/Playwright hiện hữu pass.
- **Mock gate:** user login, tạo character, start mock session, inject transcript/chat/superchat, director quyết định, fake LLM/TTS, **3D overlay thật đang render** và phát thử audio, mute hủy phát, stop sạch, reconnect không replay âm thanh cũ.
- **Real gate (sau):** OAuth YouTube thật + API quota; provider STT/TTS/LLM bằng credentials thật; benchmark voice end-of-turn → first audible audio P50/P95; nêu rõ thiết bị/browser/network.
- Luôn tách kết quả `MOCK_ONLY`, `REAL_TESTED` và `NOT_TESTED`.

## Skills index

- `repo-bootstrap`: dùng template/migration, tránh viết lại boilerplate.
- `voice-agent-reuse`: Pipecat spike và voice pipeline/interrupt.
- `youtube-events`: official OAuth/live chat/donate.
- `vrm-obs-overlay`: 3D playback, asset license, no duplicate audio.
- `conversation-director`: state/priority/memory/injection defense.
- `quality-security`: tests, performance traces, token privacy, release gates.
