# Security baselines — this service

Accepted security findings live here. Each one is **explicit, dated and
reviewable**, and CI fails once an entry is past its expiry.

This directory exists so your IaC gate can run at full severity. Without
somewhere to record an accepted finding, the only ways to deal with one are
to fix it or to delete the check — and the second is what teams actually do
under deadline pressure. The point of a baseline is to make the third option,
*accept it and say why*, cheaper than deleting the gate.

## Contract

| File | Format |
|---|---|
| `trivy-config.trivyignore` | one check id per line, `# expiry: YYYY-MM-DD  reason: …` inline or on the line above |

Enforced by `scripts/check_baselines_expiry.py`, which fails CI when an entry
is expired or carries no expiry at all. Run it yourself:

```bash
python3 scripts/check_baselines_expiry.py
python3 scripts/check_baselines_expiry.py --as-of 2027-01-01   # dry-run a date
```

**Do not use Trivy's own `expiredAt:` field.** Trivy 0.71.0 accepts it and
does not act on it — an entry dated in the past still suppresses its finding,
silently. Measured upstream; keep the `# expiry:` comment form this gate
reads.

## Adding an entry

1. Try to fix it first. Most findings that look like tool noise are not —
   upstream, 10 of 13 findings sitting below a severity threshold turned out
   to be real defects.
2. If it is genuinely not applicable, write **why**, name the compensating
   control, and give it an expiry.
3. **Verify the compensating control exists**, in the file you named. A
   justification that cites a control nobody built is worse than no
   justification: it stops the next reviewer from looking.

## Reviewing

Quarterly. For each entry, do not re-read the rationale — check the property
it depends on. If an entry says "these are append-only log buckets", confirm
they still are.

One limitation to know: the plain ignore format suppresses a check id
**repo-wide**, not per resource. An entry justified for one bucket also
silences that check everywhere. That is why each entry carries a question
about *which* resources the check currently fires on.
