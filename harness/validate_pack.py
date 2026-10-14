#!/usr/bin/env python3
"""Validate Codex project specs/skills/scenario fixtures without dependencies.

This checks the documentation pack, NOT the application implementation.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "AGENTS.md", "README.md", "CODEX_START_HERE.md",
    *[f"docs/{i:02d}_{n}.md" for i, n in enumerate([
        "BUILD_ORDER", "PRODUCT_REQUIREMENTS", "SYSTEM_ARCHITECTURE",
        "USER_EXPERIENCE", "API_EVENT_CONTRACTS", "CONVERSATION_DIRECTOR",
        "VOICE_LATENCY", "PROVIDERS_AND_INTEGRATIONS", "DATA_SECURITY_COST",
        "TESTING_ACCEPTANCE", "DECISIONS_BACKLOG", "GITHUB_REUSE_MATRIX",
        "HARNESS_AND_QUALITY_GATES", "SKILLS_AND_CODEX_WORKFLOW",
        "TEMPLATE_MIGRATION_ADR",
    ])],
    "harness/README.md", "harness/validate_pack.py",
]
REQUIRED_SKILLS = {
    "repo-bootstrap", "voice-agent-reuse", "youtube-events",
    "vrm-obs-overlay", "conversation-director", "quality-security",
}
ERRORS: list[str] = []


def check(ok: bool, error: str) -> None:
    if not ok:
        ERRORS.append(error)


for relative in REQUIRED:
    p = ROOT / relative
    check(p.is_file() and p.stat().st_size > 0, f"Required file missing/empty: {relative}")

skill_root = ROOT / ".agents/skills"
seen_skills = set()
for skill_md in sorted(skill_root.glob("*/SKILL.md")):
    raw = skill_md.read_text(encoding="utf-8")
    found = re.search(r"\A---\s*\n(.*?)\n---\s*\n", raw, re.S)
    check(bool(found), f"Invalid YAML frontmatter: {skill_md}")
    if found:
        header = found.group(1)
        match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", header, re.M)
        has_description = bool(re.search(r"^description:\s*\S.+$", header, re.M))
        check(bool(match) and has_description, f"Skill missing name or description: {skill_md}")
        if match:
            check(match.group(1) == skill_md.parent.name, f"Skill directory/name mismatch: {skill_md}")
            seen_skills.add(match.group(1))
check(seen_skills == REQUIRED_SKILLS, f"Skills mismatch, found {sorted(seen_skills)}")

scenarios = sorted((ROOT / "harness/scenarios").glob("*.json"))
check(len(scenarios) >= 8, "Need at least 8 distinct scenario fixtures")
ids: set[str] = set()
for path in scenarios:
    try:
        scenario = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ERRORS.append(f"Invalid JSON {path}: {exc}")
        continue
    check(all(k in scenario for k in ("id", "description", "initial_state", "events", "expect")), f"Missing fixture fields: {path}")
    sid = scenario.get("id")
    check(isinstance(sid, str) and sid == path.stem and sid not in ids, f"Invalid/duplicate fixture id: {path}")
    if isinstance(sid, str):
        ids.add(sid)
    check(isinstance(scenario.get("events"), list) and len(scenario["events"]) > 0, f"No scenario events: {path}")
    for event in scenario.get("events", []):
        check(isinstance(event, dict) and isinstance(event.get("type"), str) and isinstance(event.get("payload"), dict), f"Invalid event: {path}")
    check(isinstance(scenario.get("expect"), dict) and len(scenario["expect"]) > 0, f"Empty expectations: {path}")

# Prevent v1 -> v2 contradictions in hard instructions and repository architecture.
for relative in ["AGENTS.md", "README.md", "CODEX_START_HERE.md", "docs/00_BUILD_ORDER.md"]:
    p=ROOT/relative
    if p.exists():
        data=p.read_text(encoding="utf-8")
        check(not re.search(r"Next\.js App Router.*(?:required|mandatory|bắt buộc)", data, re.I), f"Next.js mandatory contradiction: {relative}")

if ERRORS:
    for issue in ERRORS:
        print("FAIL:", issue)
    sys.exit(1)
print(f"PASS: documentation + {len(seen_skills)} skills + {len(scenarios)} scenario fixtures valid")
print("NOTE: This is documentation validation only, not product tests.")
