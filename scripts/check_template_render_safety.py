#!/usr/bin/env python3
"""Contract: every file under ``templates/service/`` must parse as a Copier template.

Why this exists
---------------
``copier.yml`` sets ``_templates_suffix: ""``, which means **every** file in
the render root is a Jinja template — not just the ones that look like one.
Any file that happens to contain Jinja's delimiters is therefore a scaffolder
failure waiting to happen, and the failure is total: ``copier copy`` aborts,
so the adopter gets nothing.

Two of these landed in one afternoon, neither of them in a file anyone would
think of as a template:

* a Markdown table row whose escaped ``\\{@`` (inside a code span, inside
  documentation *about* Jinja tokens) started an expression that never closed;
* a shell script using bash's array-length syntax — a brace immediately
  followed by a hash, which is Copier's ``comment_start_string``. The
  scaffolder died with "Missing end of comment tag" pointing at a file whose
  bash was perfectly valid.

Both were caught by ``scripts/test_scaffold.sh`` in CI, which is the right
place for the *behaviour* to be checked and the wrong place to discover a
typo: that job renders a full service and takes minutes. This is the same
class of defect reduced to a parse, so it runs in pre-commit in under a
second and names the file and the line.

What this checks, and what it does not
--------------------------------------
It parses. It does not render, so it cannot catch an undefined variable or a
wrong answer file — ``test_scaffold.sh`` remains the authority for that. What
it catches is the class where the template is not even syntactically a
template, which is the class that produces confusing failures far from the
edit that caused them.

The delimiters come from ``copier.yml`` ``_envops`` rather than being
hardcoded, so changing them here changes what this checks.

Exit codes
----------
- 0: every file parses.
- 1: at least one file is not a valid Jinja template.
- 2: setup error (``copier.yml`` unreadable, or Jinja/PyYAML unavailable).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COPIER_CONF = REPO_ROOT / "copier.yml"

# Binary and vendored trees Copier itself never renders as text.
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".whl",
    ".pyc",
    ".woff",
    ".woff2",
    ".ttf",
    ".parquet",
    ".joblib",
    ".pkl",
    ".onnx",
}
SKIP_DIRS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def main() -> int:
    try:
        import yaml
        from jinja2 import Environment
        from jinja2.exceptions import TemplateSyntaxError
    except ImportError as exc:  # pragma: no cover - environment problem
        sys.stderr.write(f"::error::missing dependency: {exc}\n")
        return 2

    try:
        conf = yaml.safe_load(COPIER_CONF.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        sys.stderr.write(f"::error::cannot read {COPIER_CONF}: {exc}\n")
        return 2

    subdir = conf.get("_subdirectory")
    if not subdir:
        sys.stderr.write("::error::copier.yml declares no _subdirectory; nothing to check\n")
        return 2
    root = REPO_ROOT / subdir
    if not root.is_dir():
        sys.stderr.write(f"::error::render root {root} does not exist\n")
        return 2

    envops = conf.get("_envops") or {}
    env = Environment(
        block_start_string=envops.get("block_start_string", "{%"),
        block_end_string=envops.get("block_end_string", "%}"),
        variable_start_string=envops.get("variable_start_string", "{{"),
        variable_end_string=envops.get("variable_end_string", "}}"),
        comment_start_string=envops.get("comment_start_string", "{#"),
        comment_end_string=envops.get("comment_end_string", "#}"),
        keep_trailing_newline=True,
        # This environment only ever calls `.parse()`, so autoescape has no
        # effect on what it does. It is set anyway rather than suppressed:
        # bandit B701 is a real finding class, and a `# nosec` here would be
        # one more comment asserting a control instead of applying one.
        autoescape=True,
    )

    problems: list[str] = []
    checked = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: Copier copies it verbatim
        checked += 1
        try:
            env.parse(text)
        except TemplateSyntaxError as exc:
            rel = path.relative_to(REPO_ROOT).as_posix()
            problems.append(f"{rel}:{exc.lineno}: {exc.message}")

    if problems:
        sys.stderr.write(
            "FAIL: a file under the Copier render root is not a valid template.\n"
            '`_templates_suffix: ""` makes every file a Jinja template, so this\n'
            "aborts `copier copy` entirely — the adopter gets no service at all.\n\n"
        )
        for problem in problems:
            sys.stderr.write(f"  - {problem}\n")
        sys.stderr.write(
            "\nFix: wrap the literal text in `{% raw %}`…`{% endraw %}`, or write it\n"
            "so the delimiter never appears. Bash's array-length syntax and prose\n"
            "*about* Jinja tokens are the two that have actually bitten this repo.\n"
        )
        return 1

    print(f"[template-render-safety] OK — {checked} files under {subdir}/ parse as Copier templates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
