# Phase 2 YouTube Live runbook

## Verification status

The integration code and mocked HTTP/gRPC tests are implemented. A real Google OAuth consent and a permitted YouTube channel were not available in the development environment, so real API connectivity is `NOT_TESTED` until the checklist at the end is executed.

## Google Cloud configuration

1. Create or select a Google Cloud project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen. While the app is in testing, add each streamer account as a test user.
3. Create an OAuth client of type **Web application**.
4. Add the exact redirect URI from `GOOGLE_OAUTH_REDIRECT_URI`. Local default:

   `http://localhost:8000/api/v1/youtube/oauth/callback`

5. Set only the read-only scope:

   `https://www.googleapis.com/auth/youtube.readonly`

6. Generate a server-side encryption key:

   ```powershell
   cd backend
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

7. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `DATA_ENCRYPTION_KEY`, and the redirect URI in the backend environment. Never prefix these with `VITE_`.

## Streamer flow

1. Sign in with the existing application account.
2. Open `/settings/connections` and select **Kết nối Google an toàn**.
3. Grant the single YouTube read-only scope. The callback stores encrypted access/refresh tokens and never returns them to the browser.
4. Start a YouTube livestream with live chat enabled.
5. Open `/live`, select **YouTube thật**, select the active broadcast, choose a character, and create the session.
6. Start the session and open the same OBS overlay used by Mock Mode. Incoming events use the existing Director, FakeLLM, FakeTTS, WebSocket, and 3D playback path.

## Runtime behavior

- Primary transport: official `liveChatMessages.streamList` gRPC API.
- Fallback: official `liveChatMessages.list`; the worker waits for the returned `pollingIntervalMillis` before another request.
- The first response without a saved checkpoint is recorded as history and is not sent to the Director.
- Every provider message ID is persisted per live session. Reconnects resume from `nextPageToken`; overlapping messages are discarded.
- Super Chat and Super Sticker values preserve YouTube's `amountMicros`, currency, and display string. No currency conversion or payment processing occurs.
- Refresh tokens, access tokens, and OAuth PKCE verifiers are encrypted at rest. OAuth state is hashed, expires after ten minutes, and can be consumed once.
- Disconnect first attempts Google's revocation endpoint, then always deletes local token material and stops active ingestion.

## Dashboard error states

| Status | Meaning | Action |
|---|---|---|
| `not_configured` | Backend lacks OAuth credentials or encryption key | Configure environment and restart backend |
| `reauthorize` / `auth_expired` | Refresh failed or refresh token is missing | Use **Cấp quyền lại** |
| `insufficient_scope` | `youtube.readonly` was not granted | Reconnect and approve the requested scope |
| `chat_disabled` | Selected broadcast has live chat disabled | Enable chat or use another broadcast |
| `broadcast_ended` | YouTube reports the chat is no longer live | Stop the AI session |
| `quota_exceeded` | Google quota is exhausted | Wait for quota reset or request an appropriate quota increase; do not retry-loop |
| `reconnecting` | Transient streaming failure | Worker retries with bounded exponential backoff |
| `degraded` | Streaming API unavailable; polling fallback active | Monitor quota and connection status |

## Real API acceptance checklist

Record the Google Cloud project, channel, test time, and quota observations without recording any token.

- [ ] OAuth consent completes and `/settings/connections` shows the correct channel.
- [ ] Access token expiry causes an automatic refresh without browser token exposure.
- [ ] Active broadcast discovery shows only owned active broadcasts with live chat IDs.
- [ ] A new text message arrives once in the dashboard timeline.
- [ ] A Super Chat arrives once with exact `amountMicros`, currency, and display string.
- [ ] A Super Sticker with no user text produces a safe generic acknowledgment.
- [ ] Restart/reconnect resumes without replaying the initial chat history.
- [ ] Quota/chat-disabled/broadcast-ended errors show the documented state and stop unsafe polling.
- [ ] Disconnect revokes Google access and removes local encrypted credentials.
- [ ] Inspect backend/browser logs and bundles: no access token, refresh token, client secret, overlay key, or authorization code appears.
