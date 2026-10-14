# Harness — executable spec validation + scenario fixtures

Run at repository root:

```bash
python harness/validate_pack.py
```

Works without Node, Python extra dependencies, YouTube tokens or AI API keys. It checks document consistency, required Codex skills and fixtures **only**. It does not test the app.

**When application source exists:** implement unit/integration tests from every `harness/scenarios/*.json` in the existing **pytest** suite and Playwright E2E for actual UI/OBS playback. Update `IMPLEMENTATION_STATUS.md` accordingly. See `docs/12_HARNESS_AND_QUALITY_GATES.md`.

Fixture keys:

- `id`, `description`
- `initial_state`: `session`, `ai_muted`, `ai_speaking`, `streamer_speaking`
- `events`: array with `type`, `payload`
- `expect`: assertion object for deterministic state machine/queue/overlay outcomes

Don't generate placeholder PASS reports; fixtures are desired behavior, not evidence implemented software meets it.
