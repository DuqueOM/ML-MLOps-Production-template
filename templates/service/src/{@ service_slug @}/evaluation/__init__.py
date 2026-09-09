"""Evaluation package: base metrics + champion/challenger comparison.

``ModelEvaluator`` lives in :mod:`.metrics` and is re-exported here, so
``from .evaluation import ModelEvaluator`` — which is what ``cli.py`` writes —
resolves.

It did not. ``evaluation.py`` and this package coexisted in the same parent
package, and a package always wins over a module of the same name. So
``<slug>.evaluation`` resolved to this file, which held nothing but a
docstring: ``cli.py`` raised ``ImportError: cannot import name
'ModelEvaluator'`` on import, and the 224 lines of ``evaluation.py`` were
unreachable. It happened when ``champion_challenger.py`` was added as a
package alongside a module that was already there; this docstring has said
"base metrics + champion/challenger comparison" ever since, describing a
layout that only now exists.

``tests/test_no_module_package_shadowing.py`` makes the collision impossible
to reintroduce anywhere under ``src/``.
"""

from __future__ import annotations

from .metrics import ModelEvaluator

__all__ = ["ModelEvaluator"]
