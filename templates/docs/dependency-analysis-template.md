# Dependency Analysis: {ServiceName}

> Document known dependency conflicts and resolution strategies.
> This prevents teams from hitting the same issues repeatedly.

## Date

YYYY-MM-DD

## Environment

- Python: 3.11.x
- OS: Ubuntu 22.04 (Docker)
- pip resolver: backtracking

## Known Conflicts

### Conflict 1: {Package A} vs {Package B}

**Symptom:**
```
ERROR: pip's dependency resolver does not currently account for all packages.
{package_a} X.Y.Z requires {shared_dep}>=A.B, but {package_b} requires {shared_dep}<A.B
```

**Root Cause:**
{Explain why the conflict exists — different packages pinning incompatible ranges}

**Resolution:**
```
{shared_dep} ~= {version_that_works}  # Compatible with both A and B
```

**Risk:**
{What breaks if this resolution changes in future versions?}

### Conflict 2: numpy 2.x and joblib model loading

**Symptom:**
Models saved with numpy 1.x fail to deserialize silently or produce wrong predictions
when loaded with numpy 2.x.

**Root Cause:**
numpy 2.0 changed internal array representation. `joblib.load()` succeeds but returns
corrupted arrays for models pickled with numpy 1.x.

**Resolution:**
```
numpy ~= 1.26.0  # Pin to 1.x — NEVER allow 2.x until models are retrained
```

**Risk:**
Must retrain all models after upgrading to numpy 2.x. Cannot mix numpy versions
between training and serving environments.

## Dependency Matrix

| Package | Pinned Version | Reason | Conflicts With |
|---------|---------------|--------|---------------|
| numpy | ~= 1.26.0 | joblib model compatibility | numpy 2.x |
| scikit-learn | ~= 1.5.0 | Training + serving parity | — |
| pydantic | ~= 2.7.0 | FastAPI compatibility | pydantic 1.x |
| {package} | ~= X.Y.Z | {reason} | {conflicts} |

## Resolution Strategy

1. **Compatible release (`~=`)** for all ML packages — allows patch updates, blocks breaking changes
2. **Pin major.minor** for numpy specifically — 2.x is a silent breaking change
3. **Test in CI** with `pip check` to catch resolver conflicts early
4. **Rebuild models** when upgrading numpy or scikit-learn major versions

## Verification Commands

```bash
# Check for conflicts
pip check

# Show dependency tree
pipdeptree --warn silence

# Show what would change
pip install --dry-run -r requirements.txt
```

## Review Schedule

- **Monthly**: Check Dependabot PRs for breaking changes
- **Quarterly**: Review numpy/scikit-learn changelogs for 2.x migration readiness
- **Per-retrain**: Verify model loads correctly after any dependency update
