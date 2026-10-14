# 00 — Build order & milestones

## Quy ước

- **MUST** = bắt buộc trong MVP. **SHOULD** = làm nếu không ảnh hưởng MUST. **LATER** = ngoài MVP.
- Phase phải tạo **vertical slice** dùng được; không build toàn bộ backend trước rồi mới bắt đầu UI.
- Mỗi phase có **demo** và **exit criteria**. Không gộp 6 phase thành một PR quá lớn.

## Phase 0 — Scaffold & hợp đồng (MUST)

**Deliverables:**
- Khởi đầu từ `fastapi/full-stack-fastapi-template`: giữ `frontend/` React+Vite, `backend/` FastAPI, PostgreSQL/Auth/Alembic/Docker/Playwright/Pytest sẵn có. Bổ sung Redis, contracts, overlay route và harness; không scaffold Next.js/monorepo mới.
- Tái sử dụng Docker Compose/PostgreSQL/migrations/health có sẵn của template; **bổ sung Redis service** và `.env.example` placeholders theo thực tế. Không thay thế toàn bộ cấu hình scaffold.
- Tái sử dụng frontend shell và CI từ template; bổ sung dashboard, overlay route nền trong suốt, WS origin restrictions và hợp đồng events. Chạy baseline upstream trước khi sửa.
- Chuẩn hóa event envelope và schema Pydantic/TypeScript từ `04_API_EVENT_CONTRACTS.md`.

**Exit:** lệnh dev thực của upstream/template chạy được, API health (existing hoặc `/api/v1/health`) OK, frontend truy cập được, `python harness/validate_pack.py` và test upstream pass. Đọc `docs/12_HARNESS_AND_QUALITY_GATES.md`.

## Phase 1 — Mock end-to-end không credentials (MUST)

**Deliverables:**
- Nhân vật mẫu editable: tên, template persona, xưng hô, prompt mô tả, voice preset (mock), ảnh/VRM placeholder.
- Live session Start/Pause/Mute/Stop; một session active/user.
- Simulator ở dashboard: inject `streamer.transcript.final`, `youtube.chat.message`, `youtube.superchat`.
- Conversation Director mock với priority, cooldown, speech state, interrupt/stop, dedupe; fake LLM câu Việt theo ngữ cảnh.
- Fake TTS **tạo audio** bằng PCM sine-wave/ngữ điệu demo hoặc WAV test fixture tự tạo (không dùng asset không rõ license). Khi phát, overlay 3D có lip-sync amplitude và expression.
- Three.js + Three-VRM loader sẵn sàng; VRM hợp lệ do user cung cấp; fallback 3D procedural nếu chưa có file VRM. Nền trong suốt, aspect ratio 16:9 hoặc crop tùy OBS.
- Overlay WebSocket nhận `speech.*`, render chỉ một audio sink; dashboard KHÔNG tự playback khi live.
- Overlay connect bằng revocable token/session; countdown/recovery khi reconnect.

**Exit:** demo chạy offline end-to-end: bật session, inject streamer gọi nhân vật → fake LLM → overlay có avatar cử động và audio; inject superchat; Mute cắt audio ngay; Stop đóng session; reload overlay không replay voice cũ.

## Phase 2 — YouTube Live Auth + ingestion (MUST)

**Deliverables:**
- Google OAuth 2.0 web server flow, `youtube.readonly` tối thiểu; verify CSRF state, encrypted refresh token, revoke/disconnect.
- Liệt kê live broadcasts của chủ kênh; chọn phiên đang phát; lấy liveChatId.
- `liveChatMessages.streamList`: xử lý server-side, reconnect + `nextPageToken`, dedupe theo message ID, phân biệt text/superchat/supersticker, không phát lịch sử cũ như tin mới.
- Fallback `liveChatMessages.list` chỉ khi streamList không khả dụng và tôn trọng `pollingIntervalMillis`/quota.
- UI trạng thái Google authorization, YouTube live connected, no live found, token expired, insufficient scope/quota.

**Exit:** unit tests mapping các loại event; integration tests HTTP mock YouTube; test thực **chỉ nếu được cung cấp Google credentials và quyền kênh**, ghi rõ nếu chưa thực hiện.

## Phase 3 — Real voice input + STT (MUST)

**Deliverables:**
- Browser micro capture có user permission, chọn input device, `echoCancellation`, `noiseSuppression`; AudioWorklet tạo PCM16 mono; VAD local (Silero qua WASM/ONNX runtime hoặc wrapper được xác nhận tương thích).
- Browser gửi frames cho backend trên WS `audio`; backend stream tới STT adapter, nhận `partial`/`final`.
- Default test: Deepgram Nova-3 Streaming `language=vi`; fallback adapter configurable; mock vẫn chạy offline.
- Chống audio game lẫn mic bằng capture từ input mic độc lập (không thể hứa tách được game lọt mic); có mic meter và cảnh báo dùng tai nghe.
- Barge-in: streamer nói có độ tin cậy vượt ngưỡng -> overlay stop speaking theo chính sách.

**Exit:** test câu tiếng Việt có game audio chạy từ loa/tai nghe, đo WER/thời gian; mất kết nối STT không crash session; no audio raw persisted.

## Phase 4 — Real LLM + TTS streaming (MUST)

**Deliverables:**
- LLM adapter + prompt templating với character config, memory ngắn hạn; output streaming, giới hạn độ dài và filter untrusted inputs.
- TTS adapter streaming tiếng Việt; thử Google Chirp 3 HD; model/voice ID kiểm tra runtime.
- Audio chunk ordering, `utterance_id`, interrupt/cancel, stale response discard, overlay reconnect semantics.
- Trace các mốc latency, token/seconds/characters usage và $ ước tính theo bảng giá cấu hình (không hardcode giá không kiểm chứng).

**Exit:** live voice → STT → LLM → TTS → OBS/browser overlay thực hoạt động; P50/P95 đo và báo cáo; không claim đạt SLO nếu chưa đạt.

## Phase 5 — Memory, UX, hardening, beta (MUST/SHOULD)

**Deliverables:**
- Memory phiên live, rolling summary; long-term memory **opt-in** và dashboard review/delete.
- Character Studio có template presets và natural-language prompt input; text-based customization, chưa edit 3D advanced.
- Session quotas, rate limits, event TTL, suppression spam, health UI, cost panel, connection recovery.
- Privacy notice, secure OAuth, token rotation, observability, tests accessibility và browser/OBS compatibility.

**Exit:** tất cả test trong `09_TESTING_ACCEPTANCE.md` đạt cho mock; real provider tests kèm báo cáo; user có thể start trong ~5 bước sau khi Google OAuth/app configured. Hướng dẫn OBS Audio Monitoring và xử lý autoplay.

## LATER — Tuyệt đối không trộn vào MVP

- Vision/screenshot OBS; game recognition; TikTok; Streamlabs donate ngoài YouTube; AI auto-post to YouTube chat; OBS WebSocket scene control; subscription/payment; model 3D marketplace; avatar upload bất kỳ/rigging tự động; full VRM editor; voice cloning.

## Definition of Ready cho phase kế tiếp

- Trạng thái phase trước được ghi trong `IMPLEMENTATION_STATUS.md`.
- Config/credentials cần thiết được nêu cụ thể; có mock/fallback để chạy offline.
- API contract có schema và tests; không triển khai bằng dữ liệu hard-code vô cấu trúc.
