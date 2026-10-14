# 07 — Providers, official integrations & environment

> Tài liệu tham khảo kiểm tra ngày 2026-10-12. Provider capabilities, API formats, model availability và giá **có thể đổi**. Khi triển khai adapter, đọc lại tài liệu chính thức, pin SDK versions, không hard-code giá trong pipeline.

## Default benchmark stack (not a lock-in)

| Responsibility | Default benchmark | Fallback/mock |
|---|---|---|
| Local VAD | Silero VAD (browser, ONNX/WASM) | Simple threshold only for dev; NOT robust production |
| Streaming STT | Deepgram Nova-3 `language=vi` | OpenAI transcription adapter (chỉ dùng streaming nếu endpoint/model hỗ trợ thực) |
| LLM | FPT Marketplace `Saola-Small-32B` via streaming Chat Completions | OpenAI Responses; deterministic `FakeLlmAdapter` |
| TTS | gTTS `vi` credential-free default; Google Cloud Chirp 3 HD `vi-VN` credentialed | Experimental Edge TTS; FakeTtsAdapter |
| Web avatar | `three` + `@pixiv/three-vrm` | Procedural 3D fallback |
| YouTube | Official YouTube Data API | FakeYouTubeEventSource |

**Provider adapters không bao giờ được gọi từ client bằng API key.** Client mic PCM truyền về backend bằng authenticated socket, backend kết nối cloud. Với OAuth và lưu token, dùng server-side confidential flow.

## Google / YouTube

### Google Cloud setup cho developer

1. Tạo Google Cloud project, bật **YouTube Data API v3** (Live Streaming API methods thuộc YouTube Data API).
2. Configure OAuth consent screen/brand, authorized test users nếu app đang ở testing, verified domain khi triển khai production theo yêu cầu Google.
3. Tạo OAuth Client type **Web application**, thêm authorized redirect URI: `http://localhost:8000/api/v1/youtube/oauth/callback` hoặc public `https://domain/api/v1/youtube/oauth/callback` tùy reverse proxy; exact match.
4. YouTube permission server-side `https://www.googleapis.com/auth/youtube.readonly` trên **user account có sẵn của template**; kết hợp profile identification nếu cần. Xin offline access/refresh token theo Google policy và giữ refresh token encrypted at rest.
5. Backend gọi `liveBroadcasts.list` với `broadcastStatus=active`, `broadcastType=all`, `part=id,snippet,status`, lấy `snippet.liveChatId`; hoặc từ video URL đã xác thực lấy `videos.list(part=liveStreamingDetails)` và `activeLiveChatId`, tùy quyền và workflow. `mine` và `broadcastStatus` là hai filter loại trừ nhau; không gửi cùng request.
6. Ingest qua `liveChatMessages.streamList` low latency; reconnect bằng `nextPageToken`, dedupe; fallback `liveChatMessages.list` khi cần, sử dụng `pollingIntervalMillis`.
7. Mapper căn cứ `snippet.type`: `textMessageEvent`, `superChatEvent`, `superStickerEvent`, membership event nếu phase hỗ trợ. Tất cả text user là untrusted input. Không dùng `superChatEvents.list` để thay thế live chat streaming mặc định.
8. Handle chat disabled, broadcast ended, rate/quota errors, owner lacks live access, OAuth consent unverified; không âm thầm giả chat real.

**Chú ý:** YouTube Data API service account không được hỗ trợ như user OAuth cho kênh YouTube; MVP không được cố dùng API key duy nhất để đọc broadcasts của tài khoản user rồi giả vờ đã kết nối.

### Official docs

- OAuth server-side: https://developers.google.com/youtube/v3/live/guides/auth/server-side-web-apps
- LiveBroadcasts.list: https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/list
- LiveChatMessages.streamList: https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList
- LiveChatMessages resource: https://developers.google.com/youtube/v3/live/docs/liveChatMessages
- LiveChatMessages.list: https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list
- Videos resource activeLiveChatId: https://developers.google.com/youtube/v3/docs/videos

## Deepgram

- Nova-3 hỗ trợ `vi` và streaming; tài liệu: https://developers.deepgram.com/docs/models-languages-overview/
- Adapt WebSocket encoding, sample rate, endpointing/`interim_results`; handle `is_final` vs endpointing status cụ thể theo SDK.
- Ghi usage theo seconds audio nhà cung cấp tính, không đo chỉ bằng thời gian phiên LIVE.
- Cache Deepgram API key ở server; browser chỉ stream audio tới server; hạn chế leaking tiếng mic vào logs.

## FPT Marketplace LLM

- Official [integration guide](https://github.com/fpt-corp/ai-marketplace/blob/main/API%20Integration%20-%20Large%20Language%20Model.md) and [FPT API tutorial](https://docs.fptcloud.com/docs/fpt-ai-factory/services/serverless-inference/tutorials/call-the-api/) specify the OpenAI-compatible `POST https://mkp-api.fptcloud.com/v1/chat/completions`, Bearer authentication, `stream=true`, `choices[].delta.content` and response usage.
- The live authenticated `/v1/models` response on 2026-10-14 included `Saola-Small-32B`; its catalog token prices were used for the benchmark estimate only. The app does not hard-code those prices. Configure `FPT_LLM_INPUT_USD_PER_MILLION_TOKENS` and `FPT_LLM_OUTPUT_USD_PER_MILLION_TOKENS` after checking the current account catalog if a session cost estimate is wanted.
- `FPT_API_KEY` is backend-only. Character Studio selects an allowlisted model; the director and OBS overlay remain provider-agnostic. Missing credentials disable only the selected real provider, not Mock Mode.

## OpenAI LLM

- `gpt-5.6-luna` là một model ID có trong API docs: https://developers.openai.com/api/docs/models/gpt-5.6-luna
- Dùng text input và text output; model này **không có audio modality**, do đó STT/TTS vẫn nằm ở adapter riêng.
- Cấu hình reasoning effort thấp/none nếu API hỗ trợ để giảm latency; validate với SDK/model và benchmark chất lượng nói tiếng Việt.
- Nếu muốn đổi model, chỉ đổi `LLM_MODEL`, implementation adapter không đổi contract `synthesize_reply(context) -> AsyncIterator[str]`.
- Limits: max words/max token per response; rate limit; prompt cache có thể giúp chi phí khi character config ổn định.

## Google Cloud TTS (Chirp 3 HD)

- `vi-VN` được liệt kê trong supported languages: https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- Bidirectional streaming API: https://docs.cloud.google.com/text-to-speech/docs/create-audio-text-streaming
- Streaming `StreamingSynthesize` yêu cầu gửi streaming config trước, sau đó text chunks; audio format PCM/Opus tùy cấu hình, chuẩn hóa trước overlay.
- Chọn voice ID **thực sự xuất hiện trong list voices của project/region**, không đoán `vi-VN-*`. Tài liệu có ví dụ tiếng Anh nhưng không đồng nghĩa có cùng giọng cho tiếng Việt.
- Service account hoặc Application Default Credentials chỉ ở **server**; kiểm tra region và quota. Không nhúng service account JSON vào frontend.

## Credential-free Vietnamese TTS

- gTTS 2.5.4 is the default keyless adapter. It calls the online Google Translate speech endpoint, not Google Cloud TTS, and has no supported production SLA. Vietnamese `vi` is fixed by the allowlist.
- edge-tts 7.2.8 is optional and disabled unless `EDGE_TTS_EXPERIMENTAL_ENABLED=true`. It exposes only `vi-VN-HoaiMyNeural` and `vi-VN-NamMinhNeural` in the app allowlist. The online Edge endpoint is unofficial; failed/no-audio calls retry once and then use the existing degraded fallback.
- Both return MP3 from the remote endpoint. PyAV decodes/resamples it in memory to PCM16 mono 24 kHz. Runtime audio is not persisted, and the browser overlay remains the only audio owner.
- Local 2026-10-13 network validation: gTTS 10/10; Edge Hoài My 4/10; Edge Nam Minh 8/10. These results prove network/decoder behavior only, not human-rated naturalness or OBS playback.

## Three-VRM / VRoid asset license

- Three-VRM GitHub: https://github.com/pixiv/three-vrm (MIT code license)
- Three-VRM examples basic/expressions: https://pixiv.github.io/three-vrm/packages/three-vrm/examples/
- Library MIT **không đồng nghĩa các file model VRM hoặc texture cũng là MIT**. Mỗi model phải có license/permission thương mại riêng. Ghi `assets/LICENSE_REGISTER.md` gồm tác giả, nguồn, license, distribution rights.
- Phase 1 khi chưa có VRM thương mại hợp lệ: render **procedural mascot Three.js** để giữ MVP hoạt động; loader cho `.vrm` vẫn có test với model mà tác giả/streamer tự upload hợp lệ trong dev.
- VRoid Studio có thể hỗ trợ tạo VRM, nhưng sản phẩm MVP **không** xây VRoid clone/model editor.

## Environment variables mẫu

```dotenv
# Runtime
ENVIRONMENT=development
MOCK_MODE=true
APP_BASE_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:3000
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
POSTGRES_URL=postgresql+asyncpg://ailive:ailive@localhost:5432/ailive
REDIS_URL=redis://localhost:6379/0
SESSION_COOKIE_SECRET=replace-with-random-long-secret
DATA_ENCRYPTION_KEY=replace-with-valid-key

# Google OAuth / YouTube
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/youtube/oauth/callback
YOUTUBE_SCOPES=https://www.googleapis.com/auth/youtube.readonly
YOUTUBE_INGEST_TRANSPORT=stream

# STT
STT_PROVIDER=fake
DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-3
STT_LANGUAGE=vi

# LLM
LLM_PROVIDER=fake
OPENAI_API_KEY=
LLM_MODEL=gpt-5.6-luna

# TTS
DEFAULT_REAL_TTS_PROVIDER=gtts
GOOGLE_APPLICATION_CREDENTIALS=
GOOGLE_TTS_LANGUAGE=vi-VN
GOOGLE_TTS_VOICE_ID=vi-VN-Chirp3-HD-Leda
EDGE_TTS_EXPERIMENTAL_ENABLED=false
EDGE_TTS_VOICE_ID=vi-VN-HoaiMyNeural

# Operational limits (tuning defaults)
MAX_SESSION_HOURS=5
MAX_PROACTIVE_REPLIES_PER_HOUR=60
MAX_TTS_CHARACTERS_PER_SESSION=30000
MAX_STT_SECONDS_PER_SESSION=18000
```

**Note:** `.env.example` phải chứa placeholder, không secret thật. `MOCK_MODE=true` và mock login chỉ dùng local development, reject nếu `ENVIRONMENT=production`.

## Behavior khi chưa có credentials

- Có `FakeYouTubeEventSource` inject chat/donate, `FakeSttAdapter` nhận text simulator, `FakeLlmAdapter` trả câu tiếng Việt có template, `FakeTtsAdapter` trả audio PCM tự tổng hợp.
- Dashboard phải ghi rõ “Demo / Mock”; không dùng tín hiệu “Connected to YouTube” khi fake.
- Trong app live thật, thiếu credentials → disable đúng module, hiển thị cấu hình cần bổ sung, không crash app.

> **V2 credential discipline:** `VITE_*` values là public frontend config; chỉ chứa origin/routes, không chứa API secrets. Cần kiểm tra config `vite.config` và reverse proxy thật của template thay vì dùng env ví dụ y nguyên. Python backend dùng Google API Python client cho YouTube, không cần Node Google client.

## Phase 2 implementation record

- `google-api-python-client==2.201.0`: channels, active broadcasts, and `liveChatMessages.list` fallback.
- `grpcio==1.84.0` + `protobuf==6.33.6`: official `liveChatMessages.streamList`. The Google discovery document does not expose `streamList`; Google documents it as a separate gRPC service.
- `google-auth-oauthlib==1.5.0`: confidential web-server authorization-code flow, offline access, state and PKCE S256.
- `cryptography==50.0.2`: Fernet encryption of access/refresh tokens and PKCE verifier at rest.
- Real OAuth and live-channel traffic remain `NOT_TESTED` until credentials and a permitted channel are supplied. Fixture/mock tests are not reported as real YouTube evidence.
