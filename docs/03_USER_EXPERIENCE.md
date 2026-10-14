# 03 — UX, routes, onboarding, overlay

## Nguyên tắc UX

- Streamer muốn **vào web là dùng**: không cần tải app. Trình duyệt phải được giữ mở để lấy micro và chạy VAD; giải thích rõ ở onboarding.
- Không cho người dùng phải chỉnh >10 sliders. Bản đầu có personality preset và form mô tả tự nhiên; preset `Balanced Friend` mặc định.
- Không ẩn lỗi trong console. Mọi vấn đề mic/Google/OBS/provider được biểu thị bằng trạng thái + hành động khắc phục.
- Tất cả tính năng có thao tác `Test` không cần mở buổi live thật.

## Các route web

| Route | Màn hình | MVP |
|---|---|---|
| `/` | Landing đơn giản, CTA “Tạo AI Companion” | MUST |
| `/studio` | Danh sách nhân vật, tạo từ preset | MUST |
| `/studio/[characterId]` | Character Studio + preview/test | MUST |
| `/live` | Chọn nhân vật, YouTube channel/live, mic test và Start | MUST |
| `/live/[sessionId]` | Live dashboard và event timeline | MUST |
| `/overlay/[sessionId]?key=...` | Browser Source 3D + audio; token read-only | MUST |
| `/settings/connections` | Kết nối/ngắt Google YouTube | MUST |
| `/settings/privacy` | Xem/xóa memory, privacy settings | Phase 5 |

## Onboarding từng bước

1. **Đăng nhập** (mock account nếu MOCK_MODE; production Google OAuth). Kết nối YouTube cần quyền riêng `youtube.readonly`.
2. **Tạo nhân vật** từ một trong 3 preset: Bạn thân lém lỉnh, Trợ lý tinh tế, Đối thủ hiếu thắng. Streamer chỉnh tên, đại từ xưng hô, mức độ cà khịa dạng `nhẹ/vừa`, sở thích, những điều AI không được làm, voice preset.
3. **Kiểm tra avatar + giọng** trong Playground bằng một câu mẫu. Preview 3D fallback/VRM; lipsync hoạt động.
4. **Chọn YouTube Live** từ danh sách active broadcasts; nếu chưa live, vẫn dùng chế độ Demo; mô tả cách mở OBS và phát YouTube.
5. **Bật mic** trong dashboard; meter xác nhận đúng input, nhắc dùng tai nghe tránh game audio lọt mic.
6. **Lấy Overlay URL**, thêm **OBS → Sources → Browser → URL**, kích thước gợi ý 1280×720 hoặc 1920×1080; căn nhân vật bằng CSS/render settings, có nút test audio.
7. **Start AI**; dashboard hiển thị Listening/Thinking/Speaking/Mute và event feed.

## Dashboard Live

### Khu vực bắt buộc

- **Top status bar:** YouTube connected/disabled, Mic, OBS overlay connected, STT, AI provider, TTS, active/paused/stopped.
- **Primary controls:** Start, Pause/Resume, Mute/Unmute, Stop, Volume preview (chỉ điều khiển overlay), cấp quyền mic.
- **Event timeline:** Streamer transcript partial/final, chat, donate, AI response, lý do silence/cancel (không cần show nội dung nhạy cảm nguyên văn).
- **AI character card:** tên/ảnh/3D preview, personality short label, trạng thái đang nói.
- **Usage panel:** phút STT, số LLM calls, số ký tự TTS, chi phí ước tính, latency P50/P95 nếu có dữ liệu.
- **Settings drawer:** microphone device, tần suất AI (Balanced mặc định), donate priority, assistant name, enable memory; không thay đổi prompt hệ thống khi đang có utterance chưa hoàn thành.

### Empty/Error states

- No mic permission → “Cho phép microphone để AI nghe bạn” + bước chọn đúng device.
- No active YouTube broadcast → “Chưa có livestream đang phát”; cho demo và retry.
- OBS not connected → hiện URL overlay + hướng dẫn copy; phát tiếng AI **không** ra dashboard khi đang LIVE.
- STT provider down → hiện degraded mode, có thể tiếp tục chat/donate, không giả vờ đang nghe voice.
- Overlay autoplay/audio disabled → thông báo hướng dẫn cài Browser Source, test audio, Audio Monitoring; không tự khẳng định OBS luôn phát được audio.
- Google OAuth scope/verification problem → hướng dẫn cấu hình OAuth test users hoặc reconnect; không xin scope ghi dữ liệu không cần thiết.

## OBS Overlay

- Nền trong suốt (`alpha:true`, page body transparent), không banner/dashboard; chỉ model và trạng thái avatar.
- Góc mặc định từ ngực lên; Character Studio cho chọn thêm toàn thân, zoom vào/ra và lưu bố cục theo nhân vật để OBS dùng cùng cấu hình. Idle có nhịp thở tự nhiên; overlay hỗ trợ vẫy tay chào, tạo hình trái tim, dance loop có hẹn giờ, blink, talking mouth amplitude, cùng biểu cảm neutral/happy/angry/surprised/sad/relaxed/wink nếu VRM có blendshape tương ứng.
- Render perf: target 30fps và giảm pixelRatio khi GPU yếu; không nặng hơn mức cần thiết.
- Khi mới mở overlay: hiển thị avatar idle nhưng **không phát lại các audio phát từ trước**.
- Chỉ một audio sink trong OBS Browser Source. Dashboard test audio phải có cờ test riêng, không phát song song.
- Avatar mặc định hiện là Arcana local (VRM 0.x) theo yêu cầu operator. Metadata cấm redistribution và commercial use, nên chỉ preview development có xác thực; public build phải dùng fallback procedural cho đến khi có license phù hợp. Kira cũ dùng asset ID mặc định/retired được resolve khi đọc; không xóa persona, memory hay custom avatar. License nằm trong `assets/LICENSE_REGISTER.md`.
- UI cho streamer kiểm tra overlay bằng preview riêng; overlay URL là capability secret, không hiển thị công khai lên stream.

## OBS audio setup (thực tế)

- Browser Source có thể phát audio trong OBS; cách nghe ở tai streamer phụ thuộc cấu hình **Audio Monitoring** trong OBS. Việc Monitor and Output cùng với Desktop Audio có thể gây double audio nếu monitor route bị capture lại.
- Có bước test: AI tạo âm thanh ngắn → OBS meter hiển thị → recording test 30 giây → xác nhận viewer chỉ nghe một tiếng và streamer nghe được AI qua tai nghe.
- Không tự động đổi hệ thống âm thanh OBS; đưa hướng dẫn theo UI OBS tại thời điểm test.
- Quyền autoplay/trình duyệt nhúng có thể thay đổi theo OBS phiên bản. Kiểm tra trong OBS thực, ghi blocker nếu chỉ chạy Chrome được.

## Character Studio data entry

- Tối thiểu: `name`, `template_id`, `description`, `address_streamer_as`, `viewer_style`, `humor_level` (`low|balanced`), `proactivity` (`low|balanced`), `voice_provider`, `voice_id`, `avatar_asset_id`. Camera setup có default `avatar_camera_framing=chest-up` và `avatar_camera_zoom=1.0`; thay đổi lưu theo character.
- Cho sửa full character intro trong một textarea, nhưng không để người dùng override safety control/permissions.
- Preset là **khởi điểm editable**, không phải character cố định.
- Có Reset template và Save; bản lưu ảnh hưởng từ câu trả lời tiếp theo, không sửa nội dung lời thoại đã phát.

## Accessibility và mobile

- Dashboard tối ưu desktop stream setup, responsive cho màn hình nhỏ để điều khiển nhưng không cam kết mobile background mic.
- Nút control có keyboard focus/labels; waveform meter có text fallback.
- Text Việt rõ ràng: “Đang nghe”, “Đang tạo phản hồi”, “Đang nói”, “Đã tắt tiếng”, “Mất kết nối”, “Chờ OBS”.

> **V2 frontend implementation:** hiện thực các màn hình này bằng React + Vite/TanStack Router trong template thay vì scaffold Next.js.
