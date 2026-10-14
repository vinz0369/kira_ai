# 01 — Product Requirements Document (PRD)

## Vision

AI Live Character là **người bạn ảo 3D** dành cho livestream YouTube qua OBS. Streamer tạo nhân vật theo preset, chỉnh tên/cá tính/xưng hô/giọng, bật mic và kết nối live. AI nghe lời streamer, đọc Live Chat/Super Chat, có thể chủ động nói đúng lúc, nhưng streamer vẫn là nhân vật chính và nắm mọi quyền điều khiển.

**Không phải:** chatbot đọc tất cả comment, giải pháp tự động thay thế streamer, app Windows bắt cài, AI nhìn game trong phiên bản đầu.

## Personas và nhu cầu

- **Streamer gaming/talkshow:** muốn đối đáp tự nhiên, nhiều tương tác nhưng không bị chen lời.
- **Viewer:** thích AI có cá tính nhất quán, có thể gọi tên AI trong chat; không nghe spam.
- **Chủ kênh:** muốn setup ít, giọng Việt ổn, chi phí dễ dự báo, tắt AI tức thì.

## User stories (MUST)

| ID | User story | Acceptance criteria |
|---|---|---|
| US-01 | Tạo nhân vật từ preset | Tối thiểu 3 preset; chỉnh tên, mô tả, tính cách, xưng hô; lưu được |
| US-02 | Test nhân vật trước khi live | Sandbox inject text, nghe fake/real voice nếu khả dụng, preview avatar |
| US-03 | Kết nối YouTube | OAuth chủ kênh; chọn live đang hoạt động; chat load hoặc lỗi rõ ràng |
| US-04 | Kết nối mic | Chọn thiết bị, xin quyền, meter, hiển thị trạng thái listening, không giữ raw audio |
| US-05 | Phản hồi streamer | Khi gọi tên AI, xử lý ưu tiên, trả lời 1–2 câu, không cố đọc hết khi bị ngắt |
| US-06 | Phản hồi chat | Chọn lọc comment, anti-spam, không phản hồi từng dòng, có lý do khi im lặng |
| US-07 | Super Chat/Sticker | Nhận sự kiện, xếp hàng ưu tiên, không mất khi streamer đang nói; phân biệt tiền tệ |
| US-08 | OBS overlay | URL duy nhất cho session; 3D + TTS trong OBS; nền trong suốt; không double audio |
| US-09 | Điều khiển | Start/Pause/Mute/Stop; Mute hard-stop audio & pending; Stop revoke overlay token |
| US-10 | Cost/latency UI | Hiển thị lượt phản hồi, duration STT, usage ước tính, P50/P95 nếu đo đủ mẫu |
| US-11 | Recover | Mất WS/STT/YouTube hiển thị lỗi, thử reconnect có backoff, không replay lời cũ |
| US-12 | Privacy | Chỉ cấp quyền mic khi user chủ động bật; xóa memory đã lưu; không log secrets |

## Hành vi AI đã chốt

- Là **bạn thân**, giao tiếp thoải mái; không gọi streamer là chủ nhân/sếp trừ khi streamer cấu hình.
- Có chủ động mức **vừa phải**. Im lặng là quyết định đúng khi streamer tập trung.
- Được tranh luận, cà khịa nhẹ, tự có câu đùa; không được ghi đè điều khiển hệ thống.
- Mặc định khi streamer nói trong lúc AI phát: AI nhường lời; không giành mic.
- Khi mute bằng nút/phím tắt: cắt phát gần như ngay lập tức; lệnh qua giọng chịu độ trễ STT.
- AI phản ứng với Super Chat tự nhiên, không spam và không đọc nội dung nguy hiểm/nhạy cảm chỉ vì người gửi trả tiền.
- Mọi prompt từ chat/donate bị coi là **untrusted**.
- Avatar **3D mặc định**, dùng Three-VRM và mẫu VRM có quyền dùng thương mại; fallback procedural trong build/dev.

## Non-functional requirements

- **Performance:** mục tiêu latency streamer kết thúc lượt nói → giọng AI bắt đầu P50 ≤2.5s, P95 ≤5s. Mute bằng dashboard mong muốn <200ms tại client nhận sự kiện. Chỉ số mục tiêu, không guarantee.
- **Reliability:** dedupe chat, auto reconnect/backoff, không phát lại audio đã lỗi thời.
- **Security:** session separation, OAuth minimum scope, overlay token revocable, secrets server-side.
- **Accessibility:** giao diện tiếng Việt, keyboard controls, trạng thái màu + chữ, thông báo lỗi dễ hiểu.
- **Product UX:** streamer cần OBS Browser Source một lần, duy trì dashboard đang mở để nghe mic; hiển thị rõ yêu cầu này.
- **Cost:** đo usage, limits per session, ưu tiên giảm proactive responses khi gần quota; không đột ngột bỏ qua yêu cầu streamer nếu còn budget tối thiểu (quy tắc cấu hình).

## Mô hình 3 nguồn input

1. `streamer_voice`: transcript partial/final từ mic riêng, ưu tiên gọi trực tiếp, có VAD barge-in.
2. `youtube_chat`: comment đã chuẩn hóa, dedupe, gom nhiều câu tương tự, anti-spam.
3. `youtube_paid`: Super Chat / Super Sticker; xếp hàng và acknowledgment có thể gộp.

## MVP không bao gồm

- Chụp màn hình/camera/đọc video game; nhận diện nhân vật game.
- External donation connectors, TikTok Live, auto điều khiển OBS scenes.
- Bán skin, thuê bao, thanh toán, tự sinh model 3D, avatar marketplace.
- Đăng bình luận trở lại YouTube; không yêu cầu scope YouTube write.
- Nhân vật chiếm toàn quyền dẫn chương trình khi streamer vắng mặt; Takeover là tính năng sau.

## Definition of success (beta)

- Người mới vào hệ thống có thể tạo nhân vật → kết nối YouTube → mở mic → copy URL overlay → Start trong một quy trình dễ hiểu.
- Session mock E2E hoàn chỉnh, bản real có báo cáo benchmark & lỗi rõ ràng.
- Trong demo 10 phút gồm voice/chat/paid, AI phản hồi đúng lúc và im lặng đúng lúc, không trùng lặp, không đọc ồ ạt.
