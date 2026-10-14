import type { LiveSession } from "./liveApi"

export function sessionStatusLabel(status: LiveSession["status"]): string {
  return {
    active: "Đang chạy",
    paused: "Tạm dừng",
    draft: "Chưa bắt đầu",
    stopped: "Đã kết thúc",
  }[status]
}

export function sessionModeLabel(session: LiveSession): string {
  return `${session.mode === "youtube" ? "YouTube Live" : "Demo"} · ${session.voice_mode === "real" ? "Giọng AI thật" : "Giọng mô phỏng"}`
}

export function youtubeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: "Sẵn sàng",
    connecting: "Đang kết nối",
    connected: "Đang nhận chat",
    reconnecting: "Đang kết nối lại",
    degraded: "Kết nối không ổn định",
    chat_disabled_or_ended: "Chat cũ không khả dụng",
    chat_disabled: "Chat đã tắt",
    broadcast_ended: "Livestream đã kết thúc",
    chat_not_found: "Không tìm thấy chat",
    quota_exceeded: "Hết hạn mức YouTube API",
    auth_expired: "Cần cấp lại quyền Google",
    disconnected: "Đã ngắt kết nối",
    down: "Mất kết nối",
  }
  return labels[status] ?? "Cần kiểm tra kết nối"
}

export function friendlyLiveError(error: unknown): string {
  const detail = error instanceof Error ? error.message : String(error)
  const messages: Record<string, string> = {
    "Another live session is active":
      "Một phiên khác đang chạy. Mở phiên đó và chọn Stop trước khi bắt đầu phiên mới.",
    "Stopped session cannot restart":
      "Phiên này đã kết thúc và không thể chạy lại. Hãy tạo phiên mới.",
    "Connect YouTube first":
      "Chưa kết nối kênh YouTube. Vào Kết nối YouTube trước khi tạo phiên.",
    "Reconnect YouTube":
      "Quyền YouTube đã hết hiệu lực. Vào Kết nối YouTube để cấp lại quyền.",
    broadcast_not_active:
      "Video chưa live hoặc đã kết thúc. Kiểm tra trạng thái trong YouTube Studio rồi chọn đúng video đang phát.",
    broadcast_not_found:
      "Không tìm thấy video này trên YouTube. Kiểm tra lại liên kết livestream.",
    invalid_youtube_video:
      "Liên kết chưa đúng. Dán URL xem video YouTube, URL /live/ hoặc mã video 11 ký tự.",
    broadcast_channel_mismatch:
      "Video này không thuộc kênh Google đang kết nối. Kiểm tra kênh trong Kết nối YouTube.",
    channel_identity_missing:
      "Chưa xác định được kênh YouTube đã kết nối. Hãy kết nối lại tài khoản Google.",
    chat_unavailable:
      "Video đang live nhưng YouTube không cung cấp live chat. Kiểm tra chat đã bật và video không giới hạn người xem.",
    "Session cannot bind YouTube":
      "Chỉ có thể đổi livestream cho phiên YouTube chưa kết thúc.",
    chat_disabled_or_ended:
      "Chat của livestream cũ không còn khả dụng. Dừng phiên cũ rồi chọn livestream mới.",
    quota_exceeded:
      "YouTube API đã hết hạn mức. Chờ hạn mức được cấp lại; không cần cấp lại quyền Google.",
    quota_or_rate_limited:
      "YouTube đang giới hạn truy cập. Hãy chờ một lúc rồi thử lại.",
    rate_limited:
      "YouTube đang giới hạn tốc độ truy cập. Hãy chờ một lúc rồi thử lại.",
    auth_expired:
      "Quyền truy cập YouTube đã hết hạn. Vào Kết nối YouTube để cấp lại quyền.",
    reauthorize:
      "YouTube yêu cầu cấp lại quyền. Vào Kết nối YouTube để tiếp tục.",
    insufficient_scope:
      "Quyền Google hiện tại chưa đủ để đọc YouTube Live. Hãy cấp lại quyền.",
    "Deepgram is required for Voice Real":
      "Giọng AI thật cần Deepgram. Kiểm tra cấu hình backend hoặc chọn Giọng mô phỏng.",
    "Failed to fetch":
      "Không kết nối được server. Kiểm tra backend đang chạy, rồi thử lại.",
    "HTTP 404":
      "Server đang chạy chưa có chức năng này. Sau khi phiên live hiện tại kết thúc, cập nhật hoặc khởi động lại backend rồi thử lại.",
    "HTTP 405":
      "Server đang chạy chưa hỗ trợ thao tác này. Sau khi phiên live hiện tại kết thúc, cập nhật hoặc khởi động lại backend rồi thử lại.",
  }
  if (messages[detail]) return messages[detail]
  if (detail.startsWith("LLM provider ")) {
    return "Nhà cung cấp AI của nhân vật chưa được cấu hình trên server. Kiểm tra Character Studio và trang chẩn đoán."
  }
  if (detail.startsWith("TTS provider ")) {
    return "Giọng đọc của nhân vật chưa được cấu hình trên server. Kiểm tra Character Studio và trang chẩn đoán."
  }
  return "Không thể hoàn tất thao tác. Hãy thử lại; nếu lỗi tiếp diễn, mở trang Chẩn đoán giọng nói."
}
