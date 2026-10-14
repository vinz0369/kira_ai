---
name: quality-security
description: Enforce Codex reproducible quality gates, security checks, license tracking, real latency metrics, and precise mock-versus-production reporting.
---
# Quality / security harness

Read `docs/12_HARNESS_AND_QUALITY_GATES.md`, `docs/09_TESTING_ACCEPTANCE.md`, `docs/08_DATA_SECURITY_COST.md`.

## Procedure

1. Run `python harness/validate_pack.py`; run existing template checks from actual package scripts and Python project config.
2. Convert `harness/scenarios/*.json` to executable pytest/Playwright; don't equate fixture validation with app tests.
3. Check WebSocket ticket generation, overlay read-only token isolation/revocation, route authorization, CSRF as applicable, XSS/prompt injection boundary, secret scrubbing.
4. Verify no raw microphone audio retained by default and memory opt-in/review/delete, sensitive logging filtered and request IDs present.
5. Collect EOT → overlay playback ACK latency and P50/P95; no invented benchmarks or price claims. Collect test environment versions.
6. Validate package/asset licenses independently; check model/textures/animations including CDN redistribution rights.
7. Update `IMPLEMENTATION_STATUS.md` with commands actually run, exit codes and MOCK_ONLY vs REAL_TESTED vs NOT_TESTED.

## Done when

Tests/logs prove each claimed milestone, security checks have no known critical failures, and limitations are explicitly recorded.
