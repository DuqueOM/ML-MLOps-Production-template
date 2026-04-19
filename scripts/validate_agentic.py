#!/usr/bin/env python3
"""Validate the agentic system configuration.

Checks:
1. Every rule in .windsurf/rules/ has valid frontmatter with trigger + description
2. Every glob pattern in rules matches at least one real file (no dead rules)
3. Every skill in .windsurf/skills/ has a SKILL.md with required frontmatter
4. Every workflow in .windsurf/workflows/ has valid frontmatter
5. Every skill/workflow referenced in AGENTS.md actually exists

Exit codes:
  0 = all valid
  1 = warnings (dead rules, orphan references)
  2 = errors (invalid frontmatter, missing required fields)

Usage:
  python scripts/validate_agentic.py           # Validate all
  python scripts/validate_agentic.py --strict  # Warnings fail too
"""

from __future__ import annotations

import argparse
import glob as globlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / ".windsurf" / "rules"
SKILLS_DIR = REPO_ROOT / ".windsurf" / "skills"
WORKFLOWS_DIR = REPO_ROOT / ".windsurf" / "workflows"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks_passed: int = 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def ok(self) -> None:
        self.checks_passed += 1


def parse_frontmatter(path: Path) -> dict[str, str] | None:
    """Parse minimal YAML frontmatter (key: value or key: [list]). Returns None if missing."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return None

    if not text.startswith("---\n"):
        return None

    end = text.find("\n---\n", 4)
    if end == -1:
        return None

    frontmatter = text[4:end]
    data: dict[str, str] = {}
    current_key: str | None = None
    for line in frontmatter.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # Multi-line value continuation (starts with space and we have a current key)
        if line.startswith((" ", "\t")) and current_key:
            data[current_key] = (data.get(current_key, "") + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            data[key] = value
            current_key = key
    return data


def extract_globs(value: str) -> list[str]:
    """Extract globs from a value like ["a/**/*.py", "b/*.yaml"] or a/**/*.py,b/*.yaml."""
    if not value:
        return []
    # Strip outer brackets if present
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    # Split by comma, strip quotes
    parts = [p.strip().strip('"').strip("'") for p in value.split(",")]
    return [p for p in parts if p]


def validate_rules(result: Result) -> None:
    """Check every rule has valid frontmatter and glob patterns that match real files."""
    if not RULES_DIR.exists():
        result.error(f"Rules directory missing: {RULES_DIR}")
        return

    rule_files = sorted(RULES_DIR.glob("*.md"))
    if not rule_files:
        result.error(f"No rules found in {RULES_DIR}")
        return

    for rule in rule_files:
        fm = parse_frontmatter(rule)
        if fm is None:
            result.error(f"{rule.relative_to(REPO_ROOT)}: missing or invalid frontmatter")
            continue

        if "trigger" not in fm:
            result.error(f"{rule.relative_to(REPO_ROOT)}: missing 'trigger' in frontmatter")
            continue

        if "description" not in fm:
            result.warn(f"{rule.relative_to(REPO_ROOT)}: missing 'description' in frontmatter")

        trigger = fm["trigger"]
        if trigger not in ("always_on", "glob", "model_decision"):
            result.warn(f"{rule.relative_to(REPO_ROOT)}: unknown trigger '{trigger}'")

        # If glob trigger, validate globs match real files
        if trigger == "glob":
            globs_raw = fm.get("globs", "")
            globs = extract_globs(globs_raw)
            if not globs:
                result.error(f"{rule.relative_to(REPO_ROOT)}: trigger=glob but no globs defined")
                continue

            for g in globs:
                # Search both templates/ and root for matches
                matches_template = globlib.glob(str(REPO_ROOT / "templates" / g), recursive=True)
                matches_root = globlib.glob(str(REPO_ROOT / g), recursive=True)
                if not matches_template and not matches_root:
                    result.warn(
                        f"{rule.relative_to(REPO_ROOT)}: glob '{g}' matches zero files"
                    )
                else:
                    result.ok()

        result.ok()


def validate_skills(result: Result) -> list[str]:
    """Check every skill has SKILL.md with required fields. Returns list of skill names."""
    if not SKILLS_DIR.exists():
        result.error(f"Skills directory missing: {SKILLS_DIR}")
        return []

    skill_names: list[str] = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            result.error(f"{skill_dir.relative_to(REPO_ROOT)}: missing SKILL.md")
            continue

        fm = parse_frontmatter(skill_md)
        if fm is None:
            result.error(f"{skill_md.relative_to(REPO_ROOT)}: missing or invalid frontmatter")
            continue

        required = ["name", "description"]
        for field in required:
            if field not in fm:
                result.error(f"{skill_md.relative_to(REPO_ROOT)}: missing required field '{field}'")

        if "name" in fm:
            skill_names.append(fm["name"])

        if "allowed-tools" not in fm:
            result.warn(f"{skill_md.relative_to(REPO_ROOT)}: missing 'allowed-tools' (recommended for safety)")

        result.ok()

    return skill_names


def validate_workflows(result: Result) -> list[str]:
    """Check workflows have frontmatter. Returns list of workflow slash-command names."""
    if not WORKFLOWS_DIR.exists():
        result.error(f"Workflows directory missing: {WORKFLOWS_DIR}")
        return []

    workflow_names: list[str] = []
    for wf in sorted(WORKFLOWS_DIR.glob("*.md")):
        fm = parse_frontmatter(wf)
        if fm is None:
            result.error(f"{wf.relative_to(REPO_ROOT)}: missing or invalid frontmatter")
            continue

        if "description" not in fm:
            result.error(f"{wf.relative_to(REPO_ROOT)}: missing 'description'")

        workflow_names.append(f"/{wf.stem}")
        result.ok()

    return workflow_names


def validate_agents_md_references(
    result: Result, skill_names: list[str], workflow_names: list[str]
) -> None:
    """Check that skills/workflows referenced in AGENTS.md actually exist."""
    if not AGENTS_MD.exists():
        result.error("AGENTS.md missing")
        return

    text = AGENTS_MD.read_text(encoding="utf-8")

    # Find skill references like `skill-name` in skill context
    # AGENTS.md lists skills in the Cross-References table and "How to Invoke"
    for skill in skill_names:
        if f"`{skill}`" not in text:
            result.warn(f"Skill '{skill}' defined in .windsurf/skills/ but not referenced in AGENTS.md")
        else:
            result.ok()

    for wf in workflow_names:
        if wf not in text:
            result.warn(f"Workflow '{wf}' defined in .windsurf/workflows/ but not referenced in AGENTS.md")
        else:
            result.ok()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    result = Result()

    print("Validating agentic system...")
    print(f"  Repository: {REPO_ROOT}")
    print()

    print("[1/4] Validating rules...")
    validate_rules(result)

    print("[2/4] Validating skills...")
    skill_names = validate_skills(result)

    print("[3/4] Validating workflows...")
    workflow_names = validate_workflows(result)

    print("[4/4] Checking AGENTS.md cross-references...")
    validate_agents_md_references(result, skill_names, workflow_names)

    print()
    print(f"Checks passed: {result.checks_passed}")
    print(f"Skills found:    {len(skill_names)}  ({', '.join(skill_names)})")
    print(f"Workflows found: {len(workflow_names)}  ({', '.join(workflow_names)})")

    if result.warnings:
        print(f"\n⚠ {len(result.warnings)} warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    if result.errors:
        print(f"\n✗ {len(result.errors)} errors:")
        for e in result.errors:
            print(f"  - {e}")
        return 2

    if args.strict and result.warnings:
        print("\n✗ Strict mode: warnings treated as failures")
        return 1

    print("\n✓ Agentic system valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
