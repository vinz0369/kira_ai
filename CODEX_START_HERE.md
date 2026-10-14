# Prompt bắt đầu dành cho Codex — AI Live Character v2

Bạn đang triển khai **Web App YouTube+OBS AI Character**, sử dụng **source template có sẵn** để không làm lại hệ thống nền.

## Nhiệm vụ hiện tại: Chỉ Phase 0 và 1

1. Đọc `AGENTS.md`, `README.md`, `docs/00_BUILD_ORDER.md`, `docs/11_GITHUB_REUSE_MATRIX.md`, `docs/14_TEMPLATE_MIGRATION_ADR.md`, sau đó đọc contracts và testing tương ứng.
2. Kiểm tra repository. Nếu chỉ có tài liệu và chưa có app source, **dùng `https://github.com/fastapi/full-stack-fastapi-template` làm project base** (MIT, React/Vite + FastAPI), giữ nguyên frontend/backend/Docker/auth/test đã có. Nếu không thể fetch thì ghi blocker, không nói đã reuse. Nếu repo đang có app code, đánh giá rồi tích hợp tăng dần, không overwrite.
3. Chạy baseline checks từ upstream và `python harness/validate_pack.py`; ghi ngày, version/commit và lệnh thực tế trong `IMPLEMENTATION_STATUS.md`.
4. Tạo mock vertical slice: login/demo; Character Studio preset + chỉnh tên/persona; live session; inject fake transcript/chat/superchat; Conversation Director; FakeLlm; FakeTts **có audio thực**; WS event bus; `/overlay/:sessionId` render 3D bằng React Three Fiber + Three-VRM loader + mascot procedural fallback. Mute/Stop và reconnect phải đúng.
5. Reuse thư viện thực sự: existing template auth+DB+Docker+Playwright; `@react-three/fiber`, `@react-three/drei`, `@pixiv/three-vrm`. Chưa ép cài Pipecat ở Phase 0-1; Phase 3 mới spike Pipecat. Không dùng VRM demo không được phân phối thương mại.
6. Tạo automated tests từ `harness/scenarios`, đặc biệt P0 mute, streamer ưu tiên chat, paid event queue, TTL, viewer instruction rejection, overlay reconnect.
7. Run dev, unit, integration, UI E2E tests nếu môi trường hỗ trợ; ghi rõ test nào không chạy được. Cập nhật `IMPLEMENTATION_STATUS.md` theo format `docs/12_HARNESS_AND_QUALITY_GATES.md`.

**Không** kết nối API thật hoặc đòi API key trước khi mock slice chạy. **Không** triển khai Screenshot, TikTok, voice cloning, model 3D editor, subscription, payments, stream automation. **Không** thay frontend thành Next.js — ADR đã chọn React/Vite từ template để tránh rebuild.

Sau khi Phase 0–1 PASS với log và tests, **dừng ở milestone**, gửi status + hướng dẫn chạy local + bước tới; không tự nhận đã test YouTube hoặc OBS desktop nếu chưa test.
