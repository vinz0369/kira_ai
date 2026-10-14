# 13 — Skills for Codex: minimal set, explicit selection

Skills nằm tại `.agents/skills/<name>/SKILL.md`, có YAML frontmatter `name` và `description`. Mỗi skill chỉ hướng dẫn **một loại công việc**, không phải plugin cần cài thêm. Chúng hữu ích khi Codex làm nhiều lượt và context dài, nhưng không thay thế test hay API spec.

| Skill | Khi nào dùng | Không cần đọc khi nào |
|---|---|---|
| `repo-bootstrap` | Clone/reuse upstream, migrate app structure, auth, DB, Docker | đang sửa AI câu thoại |
| `voice-agent-reuse` | STT/LLM/TTS, VAD, Pipecat spike, stream, cancellation | chỉ chỉnh UI |
| `youtube-events` | Google OAuth, live chat, Super Chat/Sticker | 3D avatar |
| `vrm-obs-overlay` | OBS Browser Source, VRM render, speech playback | database migrations |
| `conversation-director` | priority, mute, context TTL, prompt injection, memory | chỉ chỉnh docker |
| `quality-security` | test fixtures, CI, app hardening, latency/cost/report | task đã thuộc skill chuyên ngành vẫn có thể đọc phần liên quan |

**Codex phải chọn tối đa 1–2 skills liên quan mỗi task**, tránh nạp hàng nghìn dòng prompt. Không copy skills từ repo ngoài khi chưa kiểm tra license/version. `AGENTS.md` là quy tắc xuyên suốt, skills là checklists kích hoạt theo nhiệm vụ.

## Chạy theo từng PR

- PR0: Base template usable + spec validator.
- PR1: Mock vertical slice UI/Director/Audio/OBS.
- PR2: YouTube OAuth and ingestion.
- PR3: Pipecat compatibility spike and streaming voice, decision gate.
- PR4: Production quality provider adapters/monitoring.
- PR5: Memory, constraints, beta.

Codex không được nhảy PR3 nếu PR1 chưa có automation test thật. Nếu Pipecat không phù hợp, viết `ADR-002` số đo rồi mới chọn LiveKit/loại khác.
