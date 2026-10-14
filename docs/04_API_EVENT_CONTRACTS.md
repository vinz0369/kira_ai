# 04 — REST / WebSocket / event contracts

**Version:** `v1` — schema trong tài liệu này là hợp đồng được đề xuất cho MVP. Backend Pydantic và frontend TypeScript phải chia sẻ các field names. Nếu đổi contract phải cập nhật tài liệu + tests.

## IDs và thời gian

- IDs dùng UUID v4 hoặc ULID (consistent); `event_id` globally unique; `session_id` stable per stream.
- Mọi timestamp ISO 8601 UTC với `Z` (không dùng local naive time).
- `sequence` tăng theo connection cho audio frames; `utterance_id` unique per response.
- Tất cả incoming text (`chat`, `donate`, `transcript`) được xử lý như dữ liệu không tin cậy.

## Envelope cho JSON event

```json
{
  "v": 1,
  "event_id": "018f0000-0000-7000-8000-000000000001",
  "session_id": "018f0000-0000-7000-8000-000000000002",
  "type": "streamer.transcript.final",
  "ts": "2026-10-12T07:00:00.000Z",
  "source": "voice",
  "payload": {
    "text": "Kira, mày nghĩ trận này tao thắng không?",
    "turn_id": "turn-002",
    "confidence": 0.91
  }
}
```

`source`: `voice|youtube|simulator|director|llm|tts|overlay|system`.

## Canonical incoming events

| Event type | Payload bắt buộc |
|---|---|
| `streamer.speech.started` | `{ "turn_id": "..." }` |
| `streamer.speech.ended` | `{ "turn_id": "..." }` |
| `streamer.transcript.partial` | `{ "turn_id": "...", "text": "..." }` |
| `streamer.transcript.final` | `{ "turn_id": "...", "text": "...", "confidence": 0.0 }` (`confidence` optional nếu STT không có) |
| `youtube.chat.message` | `{ "provider_message_id": "...", "author_channel_id": "...", "author_name": "...", "text": "..." }` |
| `youtube.superchat` | `{ "provider_message_id": "...", "author_name": "...", "text": "...", "amount_micros": 50000000000, "currency": "VND", "amount_display_string": "₫50,000" }` |
| `youtube.supersticker` | `{ "provider_message_id": "...", "author_name": "...", "alt_text": "...", "amount_micros": 50000000000, "currency": "VND", "amount_display_string": "₫50,000" }` |
| `session.control` | `{ "command": "start|pause|resume|mute|unmute|stop" }` |
| `overlay.connected` | `{ "connection_id": "...", "client_version": "..." }` |
| `overlay.disconnected` | `{ "connection_id": "...", "reason": "..." }` |

**Nguồn YouTube:** `amount_micros` là đơn vị một phần triệu của tiền tệ, không phải số tiền đã chuyển đổi sang VND; khi render chọn `displayString` từ YouTube nếu có và nhãn currency đúng. Trường không có `text` thì dùng chuỗi rỗng, tránh lấy `null` gây lỗi.

## Canonical outgoing events

| Event type | Payload |
|---|---|
| `session.state` | `{ "status": "active|paused|stopped|failed", "ai_muted": false, "mic_connected": true }` |
| `director.decision` | `{ "input_event_id": "...", "decision": "respond|ignore|queue|cancel", "reason_code": "...", "priority": 2 }` |
| `character.state` | `{ "mood": "neutral|happy|annoyed|surprised|sad", "speaking": false }` |
| `speech.start` | `{ "utterance_id": "...", "text": "...", "format": "pcm_s16le", "sample_rate_hz": 24000, "channels": 1, "expires_at": "...", "llm_provider": "fake|fpt|openai", "tts_provider": "fake|gtts|edge|google_chirp" }` |
| `speech.audio.meta` | `{ "utterance_id": "...", "chunk_index": 0, "byte_length": 2048 }` (nếu dùng binary frames) |
| `speech.audio` | **Phase 1 mock only:** `{ "utterance_id": "...", "chunk_index": 0, "pcm_base64": "..." }`; PCM16 mono base64 trong JSON để E2E offline, Phase 3 chuyển sang binary frame |
| `speech.end` | `{ "utterance_id": "..." }` |
| `speech.cancel` | `{ "utterance_id": "...", "reason": "barge_in|mute|stop|stale|new_priority" }` |
| `speech.playback.started` | `{ "utterance_id": "..." }` từ overlay tới server |
| `speech.playback.completed` | `{ "utterance_id": "..." }` từ overlay tới server |
| `speech.playback.cancelled` | `{ "utterance_id": "..." }` từ overlay tới server |
| `provider.health` | `{ "provider": "stt|llm|tts|youtube", "status": "ok|degraded|down", "details": "..." }` |
| `usage.update` | `{ "stt_seconds": 30, "llm_input_tokens": 1500, "llm_output_tokens": 80, "tts_characters": 50, "estimated_usd": 0.001 }` |
| `telemetry.update` | Phase 1 development diagnostics only: `{ "measurement_scope": "MOCK_SIMULATED_LOCAL", "trace_id": "...", "utterance_id": "...", "input_event_type": "...", "metrics_ms": { ... } }`; no text, audio, prompt, credential, or overlay key |

`director.decision` là diagnostic dashboard, KHÔNG gửi prompt nội bộ nhạy cảm.

The Phase 1 usage response may include bounded P50/P95 development telemetry for `event_to_decision_ms`, `llm_ms`, `tts_first_audio_ms`, `overlay_playback_ack_ms`, `event_to_first_playback_ack_ms`, and cancellation measurements. These values are explicitly labeled `MOCK_SIMULATED_LOCAL`; they do not represent real STT/LLM/TTS provider or OBS performance.

Phase 3 adds `stt_final_ms` and `voice_end_to_first_playback_ack_ms`, both rooted at server receipt of the browser VAD-end event. Usage includes `usage_measurement_scope`, per-counter `usage_basis`, `observed_session_seconds`, `projected_3h_usd`, and `projection_basis`. The three-hour projection is available only for Voice Real after at least 60 seconds with every operator rate configured. `DEGRADED_FALLBACK_LOCAL` traces are excluded from real-provider aggregate percentiles.

For credential-free gTTS/Edge selections, the TTS component of the estimate is zero and only STT/LLM operator rates are required. This is still an estimate, not a provider invoice. Both providers emit the same PCM16 binary frames as Google Chirp, so the overlay audio and lip-sync contract does not change.

## WebSocket channels

- `GET /ws/v1/dashboard/{session_id}` — auth bằng **short-lived single-use WS ticket** lấy qua authenticated REST của template, only owner; gửi control/event monitor, audio input. Ticket truyền trong WebSocket connection setup theo chính sách browser, phải scrub khỏi logs và hết hạn nhanh. Validate `Origin`.
- `GET /ws/v1/overlay/{session_id}?key=<capability>` — token read-only per-session, nhận state và speech; chỉ cho phép playback ACK, ping; tuyệt đối từ chối `session.control`, fake chat, v.v.
- Thông điệp text WS = JSON envelope như trên. Binary audio **không phải JSON**; định nghĩa transport trong `06_VOICE_LATENCY.md`.
- Heartbeat (ví dụ 15s) và timeout; reconnect exponential backoff jitter; server phát snapshot `session.state` mới nhất khi connect, không replay `speech.start` cũ.
- **Ordering:** một `utterance_id` duy nhất active/session, `speech.cancel` trước `speech.start` mới nếu có preemption. Audio chunks chỉ play khi matching current utterance.

## Đề xuất binary audio frame format

Thay vì gửi raw bytes trần không biết session/utterance, dùng header nhị phân tự mô tả:

```text
byte 0       protocol_version = 1 (uint8)
byte 1       direction/type: 0x01 mic_pcm, 0x02 tts_pcm (uint8)
byte 2..5    sequence/chunk_index (uint32 big endian)
byte 6..21   UUID bytes: turn_id (mic) / utterance_id (tts)
byte 22..N   PCM signed little-endian 16-bit mono payload
```

- Audio codec PCM16 mono; sample rate mic thương lượng qua `audio.input.config` (default 16000), TTS theo `speech.start` (provider output resample nếu cần).
- UUID trong binary header phải là **real RFC 4122 bytes**, không dùng string cắt/pad. Khi browser gửi mic partial, `turn_id` được server xác nhận qua `audio.input.config`/speech started.
- Nếu đơn giản hóa trong Phase 1 dùng **JSON base64 audio** cho mock cũng được, nhưng Phase 3 phải hoàn thiện binary frames + congestion/backpressure và sửa tài liệu nếu đổi.
- Buffer tối đa được cấu hình; trên backpressure bỏ frame im lặng, không dồn hàng phút audio. Cần đo audio gap.

## REST endpoints đề xuất

| Method | Path | Auth | Mục đích |
|---|---|---|---|
| GET | `/api/v1/health` | public, no secrets | API health |
| GET | `/api/v1/diagnostics/phase3` | authenticated app user | Safe `PREFLIGHT_ONLY` provider readiness; never returns keys, tokens, or credential paths |
| GET | `/api/v1/users/me` | template account auth | Current user (reuse route upstream; verify actual prefix/version) |
| GET | `/api/v1/youtube/connection` | authenticated app user | Safe connection/channel status; never returns tokens |
| POST | `/api/v1/youtube/oauth/authorize` | authenticated app user | Create one-use state + PKCE verifier and return Google authorization URL |
| GET | `/api/v1/youtube/oauth/callback` | one-use OAuth state | Exchange code, validate scope/channel, store encrypted tokens, redirect without code/token |
| DELETE | `/api/v1/youtube/connection` | authenticated app user | Stop ingestion, revoke Google grant, delete local tokens |
| POST | `/api/v1/auth/logout` | template auth, if applicable | Reuse upstream logout/token invalidation; do not build duplicate auth route |
| GET | `/api/v1/characters` | session | List characters |
| POST | `/api/v1/characters` | session/CSRF | Create from preset |
| PATCH | `/api/v1/characters/{id}` | owner/CSRF | Update |
| GET | `/api/v1/youtube/broadcasts` | app auth + YouTube OAuth | Owned active broadcasts with live chat IDs |
| POST | `/api/v1/youtube/broadcasts/resolve` | app auth + YouTube OAuth | Resolve `{video_url}` (watch/live/share/Studio URL or video ID); verify connected channel, live video and active chat before returning broadcast |
| POST | `/api/v1/youtube/disconnect` | session/CSRF | Revoke connection |
| POST | `/api/v1/sessions` | session/CSRF | Create draft session |
| GET | `/api/v1/sessions/` | owner | Up to 20 newest sessions (including drafts/stopped); no overlay URL/key |
| GET | `/api/v1/sessions/current` | owner | Active or paused session, or `null`; never includes overlay key/URL |
| GET | `/api/v1/sessions/{id}` | owner | State/details |
| POST | `/api/v1/sessions/{id}/control` | owner/CSRF | start/pause/resume/mute/unmute/stop |
| POST | `/api/v1/sessions/{id}/overlay-key/rotate` | owner/CSRF | Rotate token |
| GET | `/api/v1/sessions/{id}/usage` | owner | Usage metrics |
| POST | `/api/v1/sessions/{id}/simulate` | owner, MOCK_MODE only | Inject mock incoming event |
| POST | `/api/v1/sessions/{id}/youtube/reconnect` | owner, YouTube session active | Cancel existing worker and resume from persisted checkpoint |
| POST | `/api/v1/sessions/{id}/youtube/bind` | owner, non-stopped YouTube session | Verify `{video_url}` again, replace broadcast/chat and clear page checkpoint; only restart YouTube ingest, preserving voice and OBS overlay |
| GET | `/api/v1/memory` | owner | Opt-in memories |
| DELETE | `/api/v1/memory/{id}` | owner/CSRF | Delete memory |

**Auth:** kế thừa bearer/JWT của template. OAuth dùng state ngẫu nhiên được hash trong DB, one-use TTL 10 phút, PKCE S256, exact redirect URI và scope duy nhất `youtube.readonly`. Dashboard WebSocket dùng ticket ngắn hạn thay vì query long-lived JWT. YouTube consent là integration riêng trên tài khoản app đã authenticated; không thay thế template login.

### Phase 2 reconnect and dedupe

- `LiveSession.mode="youtube"` stores the selected owned broadcast ID, live chat ID, ingest status, last safe error code, and latest `nextPageToken`.
- The first `streamList`/`list` response without a checkpoint is marked historical and never enters the Director.
- With backend `YOUTUBE_CHAT_RESPONSE_MODE=all` (temporary chat-testing default), each new nonempty `youtube.chat.message` reaches the Director without requiring the character name or `?`. Safety, dedupe, bounded queue, TTL, priority and historical bootstrap rules still apply; `addressed` restores the previous filter.
- Each item is normalized then inserted into `youtubeeventreceipt` under unique `(live_session_id, provider_message_id)` before dispatch. Reconnect overlap therefore cannot double-speak paid events.
- `streamList` is primary. Fallback `list` is allowed only after streaming is unavailable and must sleep for at least the returned `pollingIntervalMillis`.
- Terminal auth, scope, quota, chat-disabled, and broadcast-ended states stop the loop and surface a `provider.health` event; transient failures use bounded exponential backoff.

## Ví dụ REST

`POST /api/v1/sessions`

```json
{"character_id":"018f0000-0000-7000-8000-000000000012","mode":"mock","youtube_broadcast_id":null}
```

Response:

```json
{"id":"018f0000-0000-7000-8000-000000000022","status":"draft","ai_muted":true,"overlay_url":"https://example.test/overlay/018f0000-0000-7000-8000-000000000022?key=REDACTED","created_at":"2026-10-12T07:00:00Z"}
```

`POST /api/v1/sessions/{id}/control`

```json
{"command":"start"}
```

Response:

```json
{"status":"active","ai_muted":false,"updated_at":"2026-10-12T07:01:00Z"}
```

- Mọi error có `{ "code":"...", "message":"Nội dung tiếng Việt", "request_id":"..." }` với status HTTP hợp lý.
- WebSocket errors có `type: system.error` và payload `code`, `retryable`, `message`; không lộ stack trace.

## Idempotency / TTL

- Incoming YouTube id: unique `(platform,provider_message_id)` trong dedupe store, TTL ≥ phiên live + grace, paid events persisted tối thiểu tới khi ack/được báo không thể phát.
- Control `mute`, `stop` idempotent; `stop` hủy generation counter và token overlay.
- Response chat tự phát có TTL 6–10s tính từ lúc nội dung còn hữu ích; donate acknowledgment có TTL lớn hơn, được gộp khi dồn dập; direct voice candidate TTL ~5s (configurable).
- Nghiêm cấm phát audio quá hạn sau reconnect.

> **V2 auth migration:** `docs/14_TEMPLATE_MIGRATION_ADR.md` quy định reuse template auth và WS ticket; ví dụ v1 về cookies/đường dẫn minh họa chỉ có hiệu lực khi phù hợp route thực tế đã được tests xác nhận.
