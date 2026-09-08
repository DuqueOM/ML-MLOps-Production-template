#!/usr/bin/env python3
"""Cross-document coherence gate for the template's enterprise documentation.

Rule 16 (`agentic/rules/16-doc-coherence.md`) + ADR-031 declare a single
source of truth for every fact that is restated across more than one
document, and forbid those restatements from drifting apart. This script is
the deterministic enforcement layer for that contract — the agentic
`doc-coherence` skill is the productivity multiplier that *fixes* drift;
this gate is what *fails CI* when drift exists (README §"agentic surface is
not load-bearing": agents accelerate, tests/CI enforce).

It is intentionally a sibling of the existing ``check_*_drift.py`` family
(``check_common_utils_drift.py``, ``check_cicd_template_drift.py``,
``check_dashboard_inventory.py``): no third-party deps, repo-root relative,
``main() -> int`` with 0/1 exit codes, one ``[doc-coherence]`` print prefix.

Checks
------
C1  Version single source of truth — ``VERSION`` must equal the latest
    *released* (dated, non-``[Unreleased]``) heading in ``CHANGELOG.md``.
C2  llms.txt version coherence — the ``> Version:`` line must reference the
    current ``VERSION`` (or carry an explicit ``legacy-snapshot`` marker).
C3  Anti-pattern count coherence — the highest ``D-NN`` defined in
    ``AGENTS.md`` must match the ``N anti-patterns`` count claimed in
    ``README.md`` and the ``(D-01 to D-NN)`` range printed in ``llms.txt``.
C4  Agentic surface counts — the live count of ``agentic/rules/*.md``,
    ``agentic/skills/*/SKILL.md`` and ``agentic/workflows/*.md`` must match
    the ``N rules + N skills + N workflows`` line in ``CLAUDE.md``.
C5  ADR traceability — every integer in ``[1 .. max ADR]`` must have a file
    in ``docs/decisions/``; a missing number is only allowed if a tombstone
    file documents it (``Status: Withdrawn``). Catches silently dropped ADRs
    and undocumented numbering gaps.
C6  Release note existence — the current ``VERSION`` must have a matching
    ``releases/vX.Y.Z.md``. ``docs/RELEASING.md`` requires one per release,
    and ``.github/workflows/release-on-tag.yml`` prefers it as the source
    for the GitHub Release title + body; without it, a tag push falls back
    to a generic, unpolished release body (the exact failure this check
    exists to catch before it ships — see that workflow's file header for
    the 2026-07-01 incident this closes).
C7  Documentation language + private-reference guard (D-37) — every file under
    ``docs/`` and every root-level ``*.md`` must be English-only and must
    never name a known private/personal repo. AUDIT R10 (2026-07-02) found
    four ``docs/audit/*.md`` files fully in Spanish and a private repo
    named in six public-repo files, once as a live clickable URL that 404s
    for any public reader. Both are the same failure mode — something true
    only in an interactive/private authoring context leaking into the
    public tree — so this check is the deterministic backstop that keeps
    it from recurring silently.

Exit codes
----------
- 0: all coherence checks pass.
- 1: at least one document has drifted from its single source of truth.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

VERSION_FILE = REPO_ROOT / "VERSION"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
LLMS = REPO_ROOT / "llms.txt"
README = REPO_ROOT / "README.md"
AGENTS = REPO_ROOT / "AGENTS.md"
CLAUDE = REPO_ROOT / "CLAUDE.md"
RULES_DIR = REPO_ROOT / "agentic" / "rules"
SKILLS_DIR = REPO_ROOT / "agentic" / "skills"
WORKFLOWS_DIR = REPO_ROOT / "agentic" / "workflows"
ADR_DIR = REPO_ROOT / "docs" / "decisions"
RELEASES_DIR = REPO_ROOT / "releases"
DOCS_DIR = REPO_ROOT / "docs"

# Case-insensitive, whole-word Spanish markers that essentially never appear
# in legitimate English technical prose. Deliberately a word list rather than
# a raw accented-character scan: this repo's own agentic/ canon legitimately
# cites accented proper nouns (e.g. "Diátaxis" the doc-taxonomy framework,
# "Cramér's V" the statistics measure) that a character scan would misflag.
#
# The accent is REQUIRED, never an optional fallback: "decisión"/"revisión"/
# "conclusión" minus their accent spell exactly the English words
# "decision"/"revision"/"conclusion" (unlike "-ción" words, which keep a
# trailing "n" where English has "-tion"). An early draft of this pattern
# made the accent optional per letter and matched nearly every English ADR
# in the repo on the word "decision" alone — caught in local testing before
# this shipped, not left as a lesson for CI to teach the hard way.
_SPANISH_MARKERS = re.compile(
    r"\b(aunque|también|además|cuáles?|cuándo|dónde|"
    r"sin embargo|por lo tanto|así como|deberían?|realiza|actualiza|"
    r"hallazgo|auditoría|alcance|fecha|integración|ingeniería|"
    r"según|entrevista|corrección(?:es)?|revisión|preguntas?|"
    r"respuesta|veredicto|decisión(?:es)?|información|"
    r"configuración|documentación|implementación|validación|"
    r"verificación|generación|resumen|conclusión|introducción|"
    r"adopción|credibilidad|infraestructura|estratégicos?|"
    r"desbalance|sobre-ingeniería)\b",
    re.IGNORECASE,
)

# Private/personal repos that must never be named in this public repo's
# documentation (AUDIT R10, 2026-07-02 — see ADR-040 for the incident this
# closes). Extend this tuple if another private companion repo is ever
# referenced. Safe to keep as a literal here: this file is Python, not
# Markdown, so it is never itself in C7's own scan scope (see
# _doc_scan_files below).
_FORBIDDEN_REPO_REFS = ("guia_mlops",)


def _norm_version(raw: str) -> str:
    """Strip a leading ``v`` and surrounding whitespace for comparison."""
    return raw.strip().lstrip("vV").strip()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def check_version_sot() -> list[str]:
    """C1 — VERSION must equal the latest released CHANGELOG heading.

    Context-adaptive (the byte-identical vendored copy also runs inside a
    scaffolded service that tracks neither file): a repo that has no version
    artefacts has no version coherence to enforce, so it is skipped. The one
    asymmetry we still flag is a CHANGELOG that records releases with no
    VERSION file — that means the single source of truth was deleted.
    """
    problems: list[str] = []
    version_raw = _read(VERSION_FILE)
    changelog = _read(CHANGELOG)
    if version_raw is None and changelog is None:
        return []  # nothing versioned here → nothing to keep coherent
    if version_raw is None:
        released = re.findall(r"^##\s*\[(v?\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
        if released:
            return [
                f"CHANGELOG.md records releases ({released[0]}) but no VERSION file exists — "
                f"the version single source of truth is missing."
            ]
        return []
    if changelog is None:
        return []  # a VERSION with no CHANGELOG to anchor against → soft skip

    version = _norm_version(version_raw)
    # Latest *released* heading: "## [vX.Y.Z] — DATE" (skip "[Unreleased]").
    released = re.findall(r"^##\s*\[(v?\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    if not released:
        return ["CHANGELOG.md has no released `## [vX.Y.Z]` heading to anchor VERSION."]
    latest = _norm_version(released[0])
    if version != latest:
        problems.append(
            f"VERSION ({version}) != latest released CHANGELOG entry ({latest}). "
            f"VERSION is the single source of truth — bump it on release or fix the heading."
        )
    return problems


def check_llms_version() -> list[str]:
    """C2 — llms.txt version line must track VERSION (or be marked legacy)."""
    version_raw = _read(VERSION_FILE)
    llms = _read(LLMS)
    if version_raw is None or llms is None:
        return []  # absence handled elsewhere
    version = _norm_version(version_raw)
    m = re.search(r"^>\s*Version:\s*([^\s|]+)", llms, re.MULTILINE)
    if not m:
        return ["llms.txt has no `> Version:` line to keep in sync with VERSION."]
    if "legacy-snapshot" in llms.lower():
        return []  # explicitly opted out of release-version tracking
    declared = _norm_version(m.group(1))
    if declared != version:
        return [
            f"llms.txt Version ({declared}) != VERSION ({version}). "
            f"Update llms.txt or mark it `legacy-snapshot` if intentional."
        ]
    return []


def _max_anti_pattern(text: str) -> int:
    nums = [int(n) for n in re.findall(r"\bD-(\d{2})\b", text)]
    return max(nums) if nums else 0


def check_anti_pattern_count() -> list[str]:
    """C3 — AGENTS max D-NN == README count == llms.txt range."""
    problems: list[str] = []
    agents = _read(AGENTS)
    readme = _read(README)
    llms = _read(LLMS)
    if agents is None:
        return []  # no canonical catalogue here → nothing to mirror
    canonical = _max_anti_pattern(agents)
    if canonical == 0:
        return []  # AGENTS.md present but defines no catalogue → nothing to check

    if readme is not None:
        m = re.search(r"(\d+)\s+anti-patterns", readme)
        if m and int(m.group(1)) != canonical:
            problems.append(
                f"README.md claims {m.group(1)} anti-patterns; AGENTS.md defines {canonical}. AGENTS.md is canonical."
            )
    if llms is not None:
        m = re.search(r"\(D-01\s*to\s*D-(\d{2})\)", llms)
        if m and int(m.group(1)) != canonical:
            problems.append(f"llms.txt prints range D-01 to D-{m.group(1)}; AGENTS.md defines D-{canonical:02d}.")
    return problems


_SURFACE_CLAIM = re.compile(r"(\d+)\s*rules\s*\+\s*(\d+)\s*skills\s*\+\s*(\d+)\s*workflows")


def _reconcile_surface(claude_path: Path, rules_dir: Path, label: str) -> list[str]:
    """Compare one CLAUDE.md's surface claim against the tree beside it."""
    claude = _read(claude_path)
    if claude is None or not rules_dir.is_dir():
        return []  # no agentic surface / no CLAUDE.md here → nothing to reconcile

    skills_dir = rules_dir.parent / "skills"
    workflows_dir = rules_dir.parent / "workflows"
    actual = (
        len(list(rules_dir.glob("*.md"))),
        len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.is_dir() else 0,
        len(list(workflows_dir.glob("*.md"))) if workflows_dir.is_dir() else 0,
    )

    m = _SURFACE_CLAIM.search(claude)
    if not m:
        return []  # doesn't claim a surface count → nothing to verify
    claimed = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if claimed != actual:
        return [
            f"{label} claims {claimed[0]} rules + {claimed[1]} skills + {claimed[2]} workflows; "
            f"the surface beside it has {actual[0]} rules + {actual[1]} skills + {actual[2]} workflows."
        ]
    return []


def check_surface_counts() -> list[str]:
    """C4 — live agentic surface counts must match CLAUDE.md's claim.

    Two CLAUDE.md files carry a surface claim, and only one of them used to
    be checked. ``templates/service/CLAUDE.md`` ships into every scaffolded
    service; inside that service this same script reconciles it correctly,
    but by then it has already shipped. It sat at "18 rules + 26 skills +
    18 workflows" against a live 19/27/20 because in the template repo
    nothing looked at it. Both are reconciled here, each against the
    surface that sits beside it.
    """
    problems = _reconcile_surface(CLAUDE, RULES_DIR, "CLAUDE.md")
    service_claude = REPO_ROOT / "templates" / "service" / "CLAUDE.md"
    service_rules = REPO_ROOT / "templates" / "service" / "agentic" / "rules"
    problems += _reconcile_surface(service_claude, service_rules, "templates/service/CLAUDE.md")
    return problems


def check_adr_traceability() -> list[str]:
    """C5 — no silent ADR gaps; every number ≤ max has a file or a tombstone."""
    if not ADR_DIR.is_dir():
        return []  # no ADR set here → nothing to keep traceable
    by_num: dict[int, Path] = {}
    for p in ADR_DIR.glob("ADR-*.md"):
        m = re.match(r"ADR-(\d{3})", p.name)
        if m:
            by_num[int(m.group(1))] = p
    if not by_num:
        return []  # directory present but empty → nothing to check
    if 1 not in by_num:
        # No ADR-001 ⇒ this is a vendored/curated subset (e.g. a scaffolded
        # service ships only the ADRs its runtime references), not the
        # canonical register that owns contiguous numbering. Gaps are expected
        # there, so the no-silent-gap rule does not apply.
        return []

    problems: list[str] = []
    for n in range(1, max(by_num) + 1):
        if n not in by_num:
            problems.append(
                f"ADR-{n:03d} is missing with no tombstone. Numbering is immutable: "
                f"add a `Status: Withdrawn` tombstone file documenting the gap (see ADR-012)."
            )
    return problems


def check_release_note_exists() -> list[str]:
    """C6 — the current VERSION has a matching releases/vX.Y.Z.md.

    Context-adaptive like the other checks: a repo with no VERSION or no
    releases/ directory (e.g. a scaffolded service) has nothing to verify
    here.
    """
    version_raw = _read(VERSION_FILE)
    if version_raw is None or not RELEASES_DIR.is_dir():
        return []
    version = _norm_version(version_raw)
    note = RELEASES_DIR / f"v{version}.md"
    if not note.is_file():
        return [
            f"releases/v{version}.md is missing for the current VERSION ({version}). "
            f"docs/RELEASING.md requires a release note per release; "
            f"release-on-tag.yml falls back to a generic body without it."
        ]
    return []


def _doc_scan_files() -> list[Path]:
    """``docs/**/*.md`` plus root-level ``*.md`` — the repo's actual prose.

    Deliberately excludes ``agentic/`` and the generated adapter surfaces
    (``.devin/``, ``.claude/``, ``.cursor/``, ``.codex/``, the
    ``templates/service/`` vendored mirror): those are operational specs for
    agents, not reader-facing documentation, and this repo's own canon
    legitimately cites accented proper nouns there (see the word-list
    comment above). Scanning only the source of truth also avoids
    triple-reporting the same finding once per mirror.

    Uses ``git ls-files`` rather than a filesystem walk so a gitignored,
    intentionally-private local file (e.g. a personal working doc kept out
    of the repo on purpose) can never be scanned — deleted branches don't
    resurrect it, working-tree scratch files don't false-positive it. Falls
    back to a plain glob if ``git`` is unavailable (e.g. a source tarball).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "*.md"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        tracked = {REPO_ROOT / line for line in out.splitlines() if line}
    except (OSError, subprocess.CalledProcessError):
        tracked = (
            set(DOCS_DIR.rglob("*.md")) | set(REPO_ROOT.glob("*.md"))
            if DOCS_DIR.is_dir()
            else set(REPO_ROOT.glob("*.md"))
        )

    def _in_scope(p: Path) -> bool:
        try:
            rel = p.relative_to(REPO_ROOT)
        except ValueError:
            return False
        return rel.parts[0] == "docs" or len(rel.parts) == 1

    return sorted(p for p in tracked if p.is_file() and _in_scope(p))


def check_doc_language_and_privacy() -> list[str]:
    """C7 — docs/ and root docs must be English-only, and name no private repo.

    Two independent guards share one check because both are the same class
    of drift: a fact true only in an interactive/private authoring context
    (a doc drafted in Spanish; a private companion repo) leaking into the
    public tree. AUDIT R10 found both at once, in the same four documents.
    """
    problems: list[str] = []
    for path in _doc_scan_files():
        text = _read(path)
        if text is None:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()

        spanish_hits = sorted({m.group(1).lower() for m in _SPANISH_MARKERS.finditer(text)})
        if spanish_hits:
            shown = ", ".join(spanish_hits[:5])
            more = f" (+{len(spanish_hits) - 5} more)" if len(spanish_hits) > 5 else ""
            problems.append(
                f"{rel} contains Spanish word(s): {shown}{more}. This repo's documentation is English-only (AUDIT R10)."
            )

        lowered = text.lower()
        for forbidden in _FORBIDDEN_REPO_REFS:
            if forbidden in lowered:
                problems.append(
                    f"{rel} references '{forbidden}', a private/personal repo that must "
                    f"never be named in this public repo's documentation (AUDIT R10)."
                )
    return problems


def check_overlay_count() -> list[str]:
    """C8 — no living document may state an overlay count that is not the real one.

    The number six was asserted against this directory in fifteen living
    places while the tree held seven.
    ``batch-only`` was consequently absent from three CI lanes, from
    ``test_scaffold.sh``, and from every test in the repository — it shipped a
    real NetworkPolicy that nothing verified. The number was not merely stale
    documentation; it was the shape of the blind spot.

    The loops that used it now discover the directory instead, so this check
    guards the remaining surface: prose. It scans living documents only —
    frozen records (CHANGELOG, VALIDATION_LOG, releases/, docs/audit/,
    docs/decisions/, MIGRATION.md) correctly describe the count at the time
    they were written, and rewriting them would make them worse records.
    """
    overlay_dir = REPO_ROOT / "templates" / "service" / "k8s" / "overlays"
    if not overlay_dir.is_dir():
        return []
    actual = sum(1 for d in overlay_dir.iterdir() if d.is_dir())
    if actual == 0:
        return [f"no overlays found under {overlay_dir} — the count cannot be checked"]

    words = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    claim = re.compile(
        r"\b(\d+|" + "|".join(words.values()) + r")\s+(?:kustomize\s+|environment\s+)?overlays\b",
        re.IGNORECASE,
    )
    frozen = (
        "CHANGELOG.md",
        "VALIDATION_LOG.md",
        "MIGRATION.md",
        "releases/",
        "docs/audit/",
        "docs/decisions/",
    )
    # Tracked files only. An untracked or ignored file — private scratch
    # notes, a virtualenv — is not a claim this repository makes.
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "*.md", "*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return ["could not list tracked files (`git ls-files`) to check overlay counts"]

    problems: list[str] = []
    for rel in sorted(tracked):
        if rel.startswith(frozen):
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = claim.search(line)
            if not match:
                continue
            token = match.group(1).lower()
            stated = int(token) if token.isdigit() else next(n for n, w in words.items() if w == token)
            if stated != actual:
                problems.append(
                    f"{rel}:{lineno}: says {match.group(0)!r}, but "
                    f"templates/service/k8s/overlays/ holds {actual}. "
                    f"A wrong count here is how `batch-only` stayed invisible to CI."
                )
    return problems


CHECKS = [
    ("C1 version-sot", check_version_sot),
    ("C2 llms-version", check_llms_version),
    ("C3 anti-pattern-count", check_anti_pattern_count),
    ("C4 surface-counts", check_surface_counts),
    ("C5 adr-traceability", check_adr_traceability),
    ("C6 release-note-exists", check_release_note_exists),
    ("C7 doc-language-privacy", check_doc_language_and_privacy),
    ("C8 overlay-count", check_overlay_count),
]


def main() -> int:
    all_problems: list[tuple[str, str]] = []
    for label, fn in CHECKS:
        for problem in fn():
            all_problems.append((label, problem))

    if not all_problems:
        # Derived, not written: this line said "all 7" while CHECKS held 8,
        # in the script whose job is catching exactly that.
        print(f"[doc-coherence] OK — all {len(CHECKS)} cross-document checks pass.")
        return 0

    print(f"[doc-coherence] {len(all_problems)} coherence violation(s):")
    for label, problem in all_problems:
        print(f"  - [{label}] {problem}")
    print("[doc-coherence] Fix with the `doc-coherence` skill or by hand, then re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
