# ADR-005: Agent Behavior Protocol + Supply Chain Security

## Status

Accepted

## Date

2026-04-23

## Context

After ADR-004 closed the data-to-training gap (EDA phase), two latent gaps remained:

1. **Agents were autonomous but not consultive.** AGENTS.md defined *what* each
   specialist agent does, but never *when* an agent must pause and ask a human.
   An agent receiving the prompt "deploy to production" would execute all the way
   through `kubectl apply` without checkpointing.

2. **Supply chain and secret hygiene were informal.** `SECURITY.md` mentioned
   gitleaks and Trivy as aspirational, but:
   - No agentic rule treated secret scanning as a hard invariant
   - Images were scanned but not signed
   - No SBOM generation (blocker for SLSA L2 compliance)
   - No admission controller to reject unsigned images in production
   - No runbook for responding to a leaked credential

Enterprise deployments — especially in regulated industries like finance and
healthcare — cannot use an MLOps template that lacks these controls. A reviewer
called out: "agents are autonomous, not consultative" and "no existe protocolo de
escalación definido". Both accurate.

## Decision

Add two interlocking systems to the agentic layer:

### System 1: Agent Behavior Protocol (AUTO / CONSULT / STOP)

Three-mode model, codified in `AGENTS.md`:

- **AUTO**: Agent executes without asking. For reversible or low-risk operations
  (scaffolding, tests, reports, training runs in dev).
- **CONSULT**: Agent proposes the plan + rationale and waits for human approval
  before executing. For operations that affect staging or shared state
  (transition model to Staging, `terraform apply staging`).
- **STOP**: Agent refuses to execute and halts. For destructive or
  compliance-bound operations (`terraform apply prod`, model promotion to
  Production, secret rotation).

Each skill's YAML frontmatter now declares `authorization_mode` per environment
or operation, and the skill body includes an "Authorization Protocol" section.

**Escalation triggers** automatically force STOP mode even from AUTO/CONSULT:

- Primary metric > 0.99 without explanation (D-06 suspicion)
- Fairness DIR in marginal range [0.80, 0.85]
- Drift PSI > 2× threshold
- Cost estimate > 1.2× monthly budget
- Any credential pattern detected
- Previously passing test now fails without code change

A **Permissions Matrix** in AGENTS.md codifies what each specialist agent can do
in dev vs staging vs prod. "Blocked" entries cannot be bypassed by human insistence
in conversation — the only path through is the governed GitHub Actions flow.

### System 2: Supply Chain Security (Cosign + SBOM + Kyverno)

CI now includes:

- `gitleaks` secret scanning on every PR (D-17)
- Hardcoded credential pattern grep (AWS keys, GCP keys, GitHub PATs) (D-17)
- IRSA/Workload Identity enforcement check on staging/prod K8s manifests (D-18)
- `syft` SBOM generation in CycloneDX + SPDX formats (D-19)
- `cosign sign --keyless` using GitHub OIDC (no key management) (D-19)
- `cosign attest` of SBOM as CycloneDX attestation (SLSA L2 component) (D-19)

Kyverno ClusterPolicy `verify-image-signatures` rejects any pod in a namespace
labeled `environment: production` whose image is not signed by the expected GitHub
Actions workflow and does not have a CycloneDX SBOM attestation.

A second Kyverno policy `require-image-digest` forbids tag-only image references
in staging/production — all images must be pinned by `@sha256:...`.

### Supporting systems

- **`common_utils/secrets.py`**: environment-aware secret loader with cloud-native
  backends (AWS Secrets Manager, GCP Secret Manager) and explicit refusal to fall
  through to `os.environ` in staging/production (D-18).
- **`common_utils/agent_context.py`**: frozen dataclasses defining the typed handoff
  contracts between specialist agents (EDAHandoff, TrainingArtifact, BuildArtifact,
  SecurityAuditResult, DeploymentRequest) + `AuditEntry` for the audit trail.
- **Skill `security-audit`**: runs before `Agent-DockerBuilder` and
  `Agent-K8sBuilder`; blocks on critical findings.
- **Skill `secret-breach-response` + workflow `/secret-breach`**: 7-phase incident
  playbook for leaked credentials (halt → classify → revoke → audit → rotate →
  clean history → notify → post-mortem).
- **Rule `12-security-secrets.md`** (`always_on`): D-17/D-18/D-19 invariants
  enforced on every file edit.

## Rationale

### Why three modes, not two (execute vs ask)

A binary "execute / ask" model conflates two very different operations:

- "Ask but I'll probably say yes" (staging deploy, model to Staging)
- "Do not even propose executing this" (prod terraform apply, silent secret rotation)

A CONSULT/STOP distinction makes the agent's expected behavior explicit. An agent
in CONSULT mode proposes a plan. An agent in STOP mode refuses and names the
governed path (PR + required_reviewers).

### Why keyless Cosign signing (OIDC), not keypair

Keyless signing uses GitHub OIDC as the identity — the signing cert's subject is
the workflow path, issuer is `token.actions.githubusercontent.com`. Benefits:

- No private key to manage, rotate, or leak (eliminates an entire D-17 attack surface)
- Identity is provable via Rekor transparency log
- Aligns with Sigstore's "trust model moved from keys to identity" direction

Tradeoff: requires Rekor network access at signing and verification time. For
fully air-gapped deploys, a BYOK model remains an option (documented in runbook
but not the template default).

### Why Kyverno over OPA Gatekeeper

Both work. Kyverno was chosen because:

- Policy syntax is YAML-native (readable by ML engineers, not only security SREs)
- Better image verification tooling via `verifyImages`
- Smaller install footprint (single controller)
- Active development, strong Sigstore integration

ADR-001 revisit trigger: if the organization standardizes on OPA for non-K8s
policies (Terraform, API, etc.), reconsider Gatekeeper for consistency.

### Why refuse os.environ for secrets in prod (D-18 strict mode)

In local dev, `os.environ` is convenient and acceptable. In prod, any secret in
`os.environ` implies either:

- A static credential injected at pod start (violates IRSA/WI)
- A credential read once and cached in RAM (fine, but how did it get there?)

Forcing production paths through `common_utils.secrets.get_secret` means:

- Rotation is observable (secret manager logs)
- The credential never lives in a process env readable by debug endpoints
- Migrating from static creds to IRSA/WI is a one-line change

### Why not adopt HashiCorp Vault now

ADR-001 explicitly deferred Vault. Revisit triggers:

- IRSA/WI insufficient (e.g., need dynamic secrets for databases)
- Multi-cloud secret federation required
- Compliance regime requires FIPS-validated secret backend

Until those triggers, AWS Secrets Manager + GCP Secret Manager with IRSA/WI is
enough and cheaper.

### Why JSONL audit log, not GitHub issues per operation

A single deploy touches many agentic operations (build, scan, sign, apply). Opening
a GitHub issue per operation would create issue spam. Instead:

- Every operation → `ops/audit.jsonl` (append-only, diffable in PRs)
- Every operation → GitHub Actions step summary (ephemeral but browsable)
- CONSULT/STOP operations → additional GitHub issue (meaningful artifact)
- Failures → additional issue tagged `audit` + `incident`

The JSONL file is small, git-tracked, and easily queryable (`jq`).

### Why dataclasses for handoff, not JSON Schema

Equivalent contract, 10× less code. Python dataclasses with `__post_init__`
validation:

- Fail fast at construction time
- Are directly usable in Python (no deserialize step)
- Are self-documenting via type hints
- `frozen=True` prevents accidental mutation (immutable handoff)

JSON Schema would add a validation step, a separate source of truth, and a file
format most ML engineers don't read fluently.

## Consequences

### Positive

- Agents are now explicitly consultative — the template delivers on "agentic"
  without being blindly autonomous
- Production deploys cannot be executed directly by any agent; all prod changes
  flow through PR + GitHub Environment approval
- Supply chain: SLSA Level 2 components are in place (signed + attested + SBOM).
  SLSA L3 (hermetic builds) remains out of scope per ADR-001 until required
- Secret leaks have a first-class incident runbook with mandatory audit trail
- IAM least-privilege is now a CI gate, not a hope
- Inter-agent handoffs are typed and validated — no more "I assumed the next
  agent would handle that field"

### Negative

- CI becomes slower: +1–2 minutes for gitleaks, syft, cosign steps per build.
  Mitigation: these run in parallel with Trivy, not serially
- Kyverno is a new cluster dependency. Mitigation: only required in staging/prod
  clusters; dev clusters can run without it
- Agents that previously executed in one step now have natural checkpoints
  in CONSULT/STOP modes. Mitigation: the checkpoint is valuable — it's the point
- Engineers accustomed to `os.environ["API_KEY"]` must migrate to the new loader.
  Mitigation: `common_utils/secrets.py` has a local-dev fallback that reads
  `os.environ`, so the migration is a one-line import change

### Mitigations

- Kyverno policies ship in `audit` mode first (can be flipped to `enforce` per
  namespace readiness). Template defaults to `enforce` for safety; first rollout
  should relax this temporarily.
- Cosign signing steps are commented out in the template CI until the user wires
  their registry (avoids broken CI on first scaffold). SBOM generation and scans
  are active by default.

## Alternatives Considered

### Alternative 1: Only add a "needs_approval: true" flag in skills

**Rejected.** Binary, insufficient. Doesn't express "refuse even if asked" (STOP)
separately from "propose and wait" (CONSULT). Doesn't cover escalation triggers.

### Alternative 2: Separate rule per cloud (AWS-specific, GCP-specific)

**Rejected.** D-17/D-18/D-19 apply to both clouds equally. Splitting creates
drift where one cloud's rule becomes stricter than the other. Single always_on
rule with per-cloud sections is simpler.

### Alternative 3: Require SLSA Level 3 (hermetic builds)

**Deferred.** Requires build service redesign (ephemeral builders, sealed
dependencies). Too heavy for a template that targets teams of 1–10 engineers.
Revisit trigger: compliance regime requires L3, OR supply chain attack on a
dependency.

### Alternative 4: Bake audit logging into every skill individually

**Rejected.** Would require 10+ skill updates and drift across skills. Instead
the `AuditEntry` dataclass is a single contract and the obligation is documented
once in AGENTS.md.

## Revisit When

- Compliance regime requires SLSA L3 or higher → revisit hermetic builds
- IRSA/WI insufficient (dynamic DB credentials, cross-cloud secret federation)
  → revisit Vault (per ADR-001)
- More than 3 production clusters → revisit central policy management (OPA
  Gatekeeper for multi-engine consistency)
- Kyverno develops breaking changes or loses maintainership → revisit Gatekeeper
- A secret leak happens despite these controls → post-mortem will identify the
  missing layer; add it in ADR-006+

## References

- ADR-001: Template Scope Boundaries (Vault, SLSA L3+ deferred here)
- ADR-002: Quality Gates and Governance (model promotion flow)
- ADR-004: EDA Phase Integration (handoff schema introduced)
- `AGENTS.md` — Agent Behavior Protocol, Handoff Schema, Audit Trail, Permissions Matrix
- `.windsurf/rules/12-security-secrets.md`
- `.windsurf/skills/security-audit/SKILL.md`
- `.windsurf/skills/secret-breach-response/SKILL.md`
- `.windsurf/workflows/secret-breach.md`
- `templates/common_utils/secrets.py`
- `templates/common_utils/agent_context.py`
- `templates/k8s/policies/kyverno-image-verification.yaml`
- `templates/cicd/ci.yml` (security-audit job, SBOM + Cosign steps)
- Anti-patterns: D-17, D-18, D-19
- External: [Sigstore Cosign](https://docs.sigstore.dev/cosign/), [Syft SBOM](https://github.com/anchore/syft),
  [Kyverno](https://kyverno.io/), [SLSA](https://slsa.dev/)
