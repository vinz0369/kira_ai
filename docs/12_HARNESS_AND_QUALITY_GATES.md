# 12 — Agent Harness / Quality Gates

## Harness là gì và tại sao cần?

**Harness** không phải mô hình AI mới. Đây là rào kiểm soát khi Codex sửa code: input fixture tái lập, command test, smoke scenario, latency tracing, skill routing và báo cáo bằng chứng. **Mục đích: tránh agent tự đánh dấu DONE khi chỉ render mock UI.**

## Files

- `harness/validate_pack.py`: chạy offline, xác thực spec files, skills frontmatter, scenario JSON và sơ đồ fixtures.
- `harness/scenarios/*.json`: dữ liệu test case cho Director và OBS. Test runner **dùng pytest/Playwright upstream**, không viết framework E2E riêng.
- `.github/workflows/spec-pack.yml`: chạy validator trên PR. Đây **chỉ là spec check**; giữ và mở rộng CI tests có sẵn của upstream.
- `.agents/skills/*/SKILL.md`: quy trình ngắn theo module, kích hoạt theo ngữ cảnh task.

## Agent loop trong Codex

1. **Assess**: kiểm tra git diff; đọc current phase, baseline test kết quả; chọn một task nhỏ.
2. **Reuse**: tìm API/component upstream đáp ứng trước khi tạo class/helper mới; đối chiếu license/version.
3. **Implement**: viết slice có UI/API/event contract + test/fixture cùng lúc, có cancel/mute semantics.
4. **Validate**: spec check → ruff/pytest → JS lint/typecheck/unit → Playwright → smoke trong Chrome và OBS nếu hỗ trợ.
5. **Observe**: ghi events và latency, dựa trên timestamps thật không phỏng đoán; check secrets/asset licenses.
6. **Report**: `IMPLEMENTATION_STATUS.md` gồm phase, commit SHA, environment, lệnh test + exit code, mock vs real, screenshots nếu tạo, blockers/next task.

## Gate tương ứng Phase

| Phase | Bằng chứng tối thiểu | FAIL nếu |
|---|---|---|
| 0 Scaffold | upstream Docker/db/auth/UI/CI baseline, docs validator | Không khởi động được template; tự tạo duplicate app |
| 1 Mock | Scenario fixtures → pytest director tests, E2E mute/stop/overlay; audio demo và 3D render thực | Hiển thị mock mà không có audio; mute không ngắt; replay audio sau reload |
| 2 YouTube | mocked API tests, `streamList`/fallback parse & dedupe, OAuth CSRF/state; kết nối thật nếu credentials có | Fake 'connected' báo là thật, duplicate paid events, token lộ |
| 3 Voice | VAD+STT tiếng Việt, partial/final, silence and turn-end, failure/reconnect, no audio persisted | Gửi desktop audio thay mic; STT nhận phản hồi của AI như streamer |
| 4 LLM/TTS | stream chunk cancel, stale discard, latency trace P50/P95, voice output no double playback | delayed 10s joke vẫn phát; TTS không cancel; thiếu trace |
| 5 Hardening | memory opt-in/review/delete; quotas/usage; OWASP auth/overlay checks; soak test | viewer điều khiển Mute; token bị log; memory không thể xóa |

## Scenarios cần thành bài test thật

Fixture format có `given` và `expect`. Codex map sang Pydantic/pytest, không cần parse mô tả bằng AI. Tất cả case kiểm tra **đúng decision/state**; text LLM cụ thể có thể fake để deterministic.

- P0 Mute/Stop preempt mọi sự kiện/utterance.
- Streamer gọi tên → priority cao, trừ khi muted/stopped.
- Chat nhắc tên AI không được bắt đầu khi streamer đang tập trung hoặc audio đã cao tải.
- Donate queue + ack một lần, không mất khi stream nói đè.
- Viewer đưa system override trong chat/donate không được mutate persona/privilege.
- Overlay reconnect chỉ gửi snapshot, không replay cũ.
- Stale event TTL không được phát.
- Budget quota đạt ngưỡng giảm proactive trước khi chặn direct chat.

## Test metrics (theo phiên LIVE)

- `end_of_turn_to_first_audible_ms`: streamer **kết thúc lượt nói** đến `speech.playback.started` từ overlay; dùng event clocks chung/correlation IDs, không chỉ đến `TTS first chunk`.
- P50 mục tiêu 2500ms; P95 mục tiêu 5000ms (benchmark target; **không fail CI giả lập dựa trên mạng thật**).
- `false_barge_in_count`, `false_response_count`, `ai_speaking_ratio`, `overlap_seconds`, `stale_replies_suppressed`.
- `stt_billed_seconds`, `llm_input/output_tokens`, `tts_characters`, `provider_estimated_usd` từ provider usage thực.
- `mic_drop_frames`, `tts_underrun`, `overlay_reconnect_count`, `youtube_duplicate_events`.

## Template-compatible quality commands

Codex cần **đọc `frontend/package.json`, `backend/pyproject.toml` và CI upstream trước** để chọn command đúng. Các ví dụ **không được giả định có tất cả scripts**:

```bash
python harness/validate_pack.py
# from template's documented working dir, examples only:
# backend: uv run pytest; uv run ruff check .
# frontend: npm run lint; npm run build; npm run test (if added)
# e2e: npx playwright test (use existing upstream config)
```

Khi chưa có ứng dụng nguồn, chỉ có `validate_pack.py` là chạy được. CI gate ở pack này không phải bằng chứng sản phẩm đã hoàn thiện.

## IMPLEMENTATION_STATUS.md đề xuất

```md
# Implementation Status
- Date/commit:
- Upstream template commit/tag:
- Phase: 0 / 1 / ...
- Mode: MOCK_ONLY / REAL_TESTED / NOT_TESTED
- Completed vertical slice:
- Reused repositories and pinned versions:
- Commands actually run + exit code:
- Manual OBS test performed? device, OBS version, steps:
- Metrics P50/P95 (if real):
- Security/license checks:
- Known failures/blockers:
- Next smallest task:
```
