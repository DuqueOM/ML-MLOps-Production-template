---
paths:
  - "**/training/*.py"
  - "**/models/*.py"
  - "**/features/*.py"
---

# ML Training Rules

## Pipeline (mandatory sequence)
load → validate (Pandera) → features → split → cross-validate → evaluate → fairness → save → mlflow → gates

## Quality Gates (ALL must pass — D-12)
- Primary metric >= threshold, no regression > 5% vs production
- Fairness: DIR >= 0.80 per protected attribute
- Leakage: metric < 0.99 → investigate before promoting (D-06)
- Latency: P95 <= 1.2x current production

## Key Rules
- Feature engineering fit on train only, transform on val/test
- Compatible release pinning (`~=`) for all ML packages (D-05)
- SHAP background data must have both classes (D-07)

## Required Tests
- `test_no_data_leakage()`, `test_shap_consistency()`, `test_fairness_disparate_impact()`

See `AGENTS.md` for anti-pattern table D-01 to D-12.
