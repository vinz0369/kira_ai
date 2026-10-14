---
name: youtube-events
description: Add official YouTube OAuth account integration, livestream chat, Super Chat and Super Sticker event ingestion with deduplication and secure token handling.
---
# YouTube event ingestion

Read `docs/07_PROVIDERS_AND_INTEGRATIONS.md`, `docs/04_API_EVENT_CONTRACTS.md`, and `docs/08_DATA_SECURITY_COST.md`.

## Procedure

1. Start with `FakeYouTubeEventSource` and fixtures; do not require Google credentials for Phase 0/1.
2. Reuse existing template account auth; YouTube OAuth is separate scoped consent. Verify state, PKCE if applicable, exact redirect URI, token encryption, disconnect/revoke.
3. Implement official `liveBroadcasts.list` / `videos.list` to identify liveChatId; inspect official Python SDK capability for `liveChatMessages.streamList`; prefer official streaming, fallback to official `list` respecting polling interval.
4. Map chat, Super Chat and Super Sticker into canonical events with `provider_message_id` and accurate `amount_micros`/currency.
5. Persist idempotency watermark and paid-event ack state; reconnect must not rebroadcast old items. Handle quota, disabled chat, expired token, broadcast ended.
6. Treat viewer text as untrusted data; no user chat controlling system prompts, muting or memory.

## Done when

Mock mapper tests pass; real OAuth and live chat are tested only when a permitted channel exists; status clearly says MOCK or CONNECTED, never fabricated.
