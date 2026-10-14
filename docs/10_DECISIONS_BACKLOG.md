# 10 — Product decisions, boundaries & later backlog

## Accepted decisions (do not re-ask unless technically blocked)

| Area | Decision |
|---|---|
| Platforms | YouTube LIVE + OBS Studio (not TikTok yet) |
| Delivery | Web app; streamer dislikes installing applications/extensions |
| Character role | AI as independent conversational friend, streamer controls stage/system |
| Inputs for MVP | Streamer microphone, YouTube Live Chat, YouTube Super Chat/Super Sticker |
| Vision | Screenshot/game vision explicitly postponed |
| Conversation | AI always listens when session/mic on, selectively speaks; default moderate proactivity |
| Interrupt | Streamer voice has precedence; muted by owner always wins |
| Personality | User freely customizes character **starting from provided presets** |
| Memory | Short-term context for performance; persistent memory opt-in/review/delete |
| 3D | 3D by default, use Three-VRM + pre-existing licensed VRM, minimal animation; no custom 3D engine |
| Monetization | Future premium skins, voices, templates, subscription; not MVP |
| Latency/cost | Low latency prioritized; streaming STT/LLM/TTS with adapters; cost-conscious, not every event triggers LLM |
| Voice language | Vietnamese first; gaming slang and Vietnamese-English mix |

## Assumptions used to unblock development

- Web session must stay open to keep microphone stream; explicit UI notice.
- Frontend **React+Vite/TypeScript từ FastAPI Full Stack Template** (ADR-001 v2 thay Next.js); backend FastAPI/Python + SQLModel; PostgreSQL/Redis; tận dụng Docker/CI/auth upstream.
- Google OAuth server-side read-only scope for selecting user's own broadcast; no chat write permission.
- Default model/provider choices are **benchmark defaults, replaceable**, not product-wide contracts.
- One active session per user in MVP; overlay URL is revocable bearer-like secret.
- LLM character says 1–2 sentences in typical reply, with occasional longer reply only when direct user request.
- Prioritize correctness/control over aggressive AI chatter. When voice/audio uncertain, safe fallback = silence.
- Dashboard fake sandbox is a first-class way to develop without API keys.

## Known technical uncertainties — measure, do not guess

1. Browser microphone VAD STT accuracy with noisy gaming mic, especially headphones/desktop audio cross-talk.
2. OBS Browser Source CEF audio autoplay and Audio Monitoring behavior across versions; must do manual QA.
3. Real-world `YouTube streamList` behavior through selected Python SDK and quota/reconnect; verify production permissions.
4. Google Chirp 3 HD `vi-VN` quality, streaming first-byte latency and availability of selected voice ID in actual project.
5. Deepgram Nova-3 Vietnamese hotword/turn-end behavior for slang and names.
6. Provider price/quotas and egress cost at time of launch.
7. AudioWorklet, background-tab throttling, OS microphone permissions, browser-specific constraints.
8. VRM model distribution and commercial license; Three-VRM library license is separate from assets.

## Explicitly deferred features

- **Vision:** screenshot OBS every 5–10 min + event-trigger capture with explicit consent, **after MVP**.
- **Takeover Mode:** AI temporarily hosts stream while streamer steps away; requires separate approval/workflow.
- **TikTok Live/other platforms:** different API connectors, not now.
- **External donations:** Streamlabs and other platforms as integrations, not now.
- **Character store:** premium VRM skins, model uploads, advanced customization/rigging, commercial licenses.
- **Voice store:** premium Vietnamese voice packs, unique voices, licensing.
- **Realtime multi-model streaming:** switch provider depending on latency/cost; benchmark first.
- **Viewer memory profiles:** only with explicit opt-in/privacy design, not MVP.
- **Auto post YouTube chat:** separate scope and safety controls, not part of first version.
- **Payment/subscription SaaS:** after validating live use and provider unit economics.

## Scope-change guardrail

If Codex identifies a “nice-to-have”, record it here under Later Backlog. Do not implement until basic session voice/chat/donate with OBS audio and owner controls works.

## Next decision after MVP functioning

Conduct 10 live user tests on OBS with Vietnamese streamers and measure: latency, false interrupts, annoying comment rate, perceived 3D character personality, costs/session. Choose final STT/TTS providers based on measured trade-offs, not marketing claims.

## V2 decisions 2026-10-12
- Adopt full-stack-fastapi-template React/Vite as base scaffold (ADR-001), tránh Next.js rebuild.
- Candidate Pipecat before custom voice engine; LiveKit Agents comparison only if needed, decision pending spike.
- Harness + skills added, no arbitrary custom testing framework, extend pytest/Playwright.
