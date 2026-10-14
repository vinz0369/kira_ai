# 08 — Data model, security, privacy & cost control

## Minimal database schema (PostgreSQL)

### `users`

- `id UUID PK`, `google_subject unique nullable` (mock users isolated), `display_name`, `created_at`, `updated_at`.

### `oauth_connections`

- `id`, `user_id FK`, `provider='google_youtube'`, `encrypted_access_token` (optional short-term), `encrypted_refresh_token` (optional), `expires_at`, `granted_scopes`, `provider_channel_id`, `created_at`, `updated_at`.
- Token at rest encryption via server key/KMS. Never return tokens to client.

### `characters`

- `id`, `user_id FK`, `name`, `template_id`, `persona_description`, `address_streamer_as`, `viewer_style`, `humor_level`, `proactivity`, `voice_provider`, `voice_id`, `avatar_asset_id`, `memory_opt_in`, `created_at`, `updated_at`.
- `avatar_asset_id` references licensed asset; don't store an arbitrary remote URL without allowlist/security validation.

### `live_sessions`

- `id`, `user_id FK`, `character_id FK`, `broadcast_id nullable`, `live_chat_id nullable`, `status`, `ai_muted`, `started_at`, `stopped_at`, `created_at`, `last_seen_at`, `session_epoch`, `overlay_key_hash`.
- Unique partial index `(user_id) WHERE status IN ('active','paused')` for single active live.

### `paid_events`

- `id`, `live_session_id`, `provider_event_id`, `event_type`, `author_display_name`, `amount_micros`, `currency`, `ack_status='pending|acknowledged|skipped'`, `created_at`; unique `(live_session_id,provider_event_id)`.
- Paid event does not mean direct money flows through our app; no payment card details.

### `memory_items` (only opt-in)

- `id`, `user_id`, `character_id`, `content`, `source`, `confidence`, `created_at`, `updated_at`, `deleted_at`.
- Never store sensitive viewer profiling by default. Limit length/age and support user delete.

### `usage_counters`

- `id`, `session_id`, `stt_seconds`, `llm_input_tokens`, `llm_output_tokens`, `tts_characters`, `provider_estimated_cost_usd`, `updated_at`.
- Optional separate time-series metrics in Redis/Prometheus. Do not persist raw audio or full transcript by default.

## Ephemeral data in Redis

- `session:{id}:state` latest state (TTL + lease)
- `session:{id}:events` recent sanitized events (bounded TTL)
- `session:{id}:chat_dedupe` processed YouTube message IDs (session TTL)
- `session:{id}:speech` current utterance state, epoch, queue
- `session:{id}:context` rolling transcripts and session summary

Retention defaults for initial implementation:
- Raw mic audio: **never persisted**; in-memory ring buffer only for streaming/pre-roll, zero on stop.
- Voice transcript/chat used as context: Redis TTL short (e.g. max 24h) and bounded; do not transfer to permanent DB unless user opt-in memory extraction.
- Structured session usage metrics: keep for billing/debug for defined period, no content.
- Paid event metadata: only necessary to dedupe/ack and support user-facing history, define retention in policy and delete option.

## Security controls

1. **Google OAuth:** server flow, state CSRF, minimal scopes (`youtube.readonly`), refresh token encrypted. User can disconnect and revoke token.
2. **Sessions:** reuse user authentication của template (JWT/bearer hoặc cookie tùy version pin); access token có TTL ngắn và refresh policy; nếu sử dụng cookie thêm SameSite/Secure/HttpOnly + CSRF, nếu dùng bearer header bổ sung kiểm soát XSS. Với WS dùng **short-lived one-time ticket** phát sau khi user được xác thực, có Origin + ownership checks. Không tạo auth layer song song.
3. **Overlay URL token:** cryptographically random ≥128-bit, stored hashed, scoped to single live session, revocable/rotatable; no control permissions; avoid tokens in log, analytics, referrer via `Referrer-Policy: no-referrer` and restricted CSP. Copy warning in UI.
4. **Socket isolation:** validate owner/session ID for dashboard, capability for overlay, check Origin, rate-limit and reject unknown event types. Overlay does not inject fake streamer/chat events.
5. **Upload safety:** MVP no arbitrary VRM uploads from internet; if enabled later enforce file size, MIME, path, CORS, sandbox and licenses.
6. **Prompt injection:** chat/donate/transcript untrusted, cannot override hard directives or execute code/system actions.
7. **Cost abuse:** daily/session caps, event rate limiting, char/token caps, no massive TTS for malicious user text, bounded queues.
8. **Log hygiene:** no API keys, Google tokens, raw audio, private transcripts, overlay capability or PII dumps; log reason codes and trace metadata.
9. **Web safety:** HTTPS/WSS production, CORS exact allowlist, Content Security Policy, safe `noopener`, input escaping, no arbitrary HTML rendered from chat.
10. **Failure:** Redis/provider fail-closed for speaking/control, proper errors; never silently continue ungoverned autonomous bot.

## API usage / cost calculations

Cost is **dynamic/configurable**. For each session:

```text
stt_cost = actual_billable_stt_seconds / 60 * provider_price_per_minute
llm_cost = input_tokens / 1_000_000 * input_price_per_million
         + output_tokens / 1_000_000 * output_price_per_million
         + any non-token fees (if applicable)
tts_cost = billable_characters / 1_000_000 * provider_price_per_million_characters
        (or provider-specific metric)
provider_cost_total = sum + other billable provider calls
```

- Giá nhà cung cấp thay đổi, token cache/free tier có thể áp dụng; dashboard hiển thị “**ước tính**” cho tới khi đối soát hóa đơn. Không cứng chi phí $1.26/3h vào code.
- Tách usage STT active audio, time actually billed, LLM input/output/extra, TTS provider-specific counters.
- Budgets: max session duration, max proactive responses/hour, max STT seconds, max TTS characters, max total estimated USD; expose visual progress.
- Near budget: giảm P3 trước, giữ P1 nếu vẫn đủ ngân sách cấu hình; khi budget hard cap đạt, disable provider calls và show rõ trạng thái.
- Admin/runbook: rotation keys, revoke Google connection, delete memories/account, audit OAuth scopes, inspect quota (no exposed secrets).

## Privacy disclosure người dùng

- Web app nghe mic **chỉ khi bật quyền và đang chạy session voice**; raw audio được truyền tới bên cung cấp STT để nhận dạng khi bật tính năng, không lưu lại trong sản phẩm mặc định.
- Nội dung chat/donate được gửi tới hệ thống AI khi cần để tạo phản hồi, có thể đi qua LLM/TTS third parties.
- Streamer có lựa chọn tắt long-term memory; mô tả nơi lưu và thời hạn; có nút xóa.
- Viewer identity không được âm thầm xây dựng profile dài hạn trong MVP.

> **V2 auth reconciliation:** yêu cầu auth của API/WS theo ADR-001; không tạo hệ thống user auth song song với template. Đặc biệt đánh giá rủi ro lộ overlay URL qua logs, history và referrer.
