# Runbook — Kyverno Admission Validation (kind cluster)

- **Authority**: ADR-020 §S1-4, R4 audit finding H7.
- **Mode**: **STOP — delegated** (Platform / Security executes).
- **Approver**: Platform Lead.
- **Audit trail**: every execution writes an entry to `VALIDATION_LOG.md` and an `AuditEntry` to `ops/audit.jsonl`.

---

## Why this runbook exists

R4 finding **H7** flagged that Kyverno admission policies under `templates/k8s/policies/` were never validated against a
real cluster — i.e., we had never observed the webhook reject an unsigned image or a pod without an SBOM attestation.
The YAML looked correct; that was the entirety of the assurance.

This runbook produces evidence in three forms:

1. A pod referencing an UNSIGNED image MUST be admission-rejected with a clear reason.
2. A pod referencing an image WITHOUT an SBOM attestation MUST be admission-rejected.
3. A pod referencing a properly signed + attested image MUST be admitted.

The procedure runs entirely on `kind` (Kubernetes-in-Docker), no cloud account required.

---

## Why STOP-delegated

The procedure is non-destructive (kind is a throwaway local cluster), but
it produces signed artifacts that touch the supply-chain trust chain. To
preserve the audit trail discipline:

1. The procedure MUST NOT be executed by an autonomous agent.
2. The signing keys used (Cosign keyless via Sigstore Fulcio) write to
   the public Rekor transparency log; the signing identity is the human
   operator's GitHub identity, recorded in the audit entry.

---

## Pre-conditions

- `docker` >= 24.x running.
- `kind` >= 0.20.0 (`kind version`).
- `kubectl` >= 1.29.
- `kustomize` >= 5.0.
- `cosign` >= 2.2 (`cosign version`).
- `syft` >= 1.0 (`syft version`).
- A local OCI registry running on `localhost:5000` (kind's recommended pattern):

  ```bash
  docker run -d --restart=always -p 5000:5000 --name kind-registry registry:2
  ```

- Network access to Sigstore (`fulcio.sigstore.dev`, `rekor.sigstore.dev`).
- Approval recorded; ticket ID assigned.

---

## Procedure

### Step 1 — Spin up a kind cluster

```bash
cat > /tmp/kind-r4-config.yaml <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5000"]
    endpoint = ["http://kind-registry:5000"]
nodes:
- role: control-plane
  kubeadmConfigPatches:
  - |
    kind: ClusterConfiguration
    apiServer:
      extraArgs:
        feature-gates: "ValidatingAdmissionPolicy=true"
EOF

kind create cluster --name r4-kyverno --config /tmp/kind-r4-config.yaml
docker network connect kind kind-registry || true

kubectl cluster-info --context kind-r4-kyverno
```

### Step 2 — Install Kyverno

```bash
helm repo add kyverno https://kyverno.github.io/kyverno/
helm repo update
helm upgrade --install kyverno kyverno/kyverno \
  --namespace kyverno --create-namespace \
  --version 3.2.x \
  --set admissionController.replicas=1 \
  --wait

kubectl -n kyverno get pods
# Expected: kyverno-admission-controller-* Running
```

### Step 3 — Apply repo's policies

```bash
REPO_ROOT=/path/to/repo
kubectl apply -k "${REPO_ROOT}/templates/k8s/policies/"

kubectl get clusterpolicy
# Expected: at least require-image-signature, require-sbom-attestation,
# disallow-latest-tag (names per the policy YAML).
```

### Step 4 — Build, push, sign, attest a TEST image (good case)

```bash
TEST_IMAGE=localhost:5000/r4-admission-test:smoke
docker build -t "${TEST_IMAGE}" \
  -f "${REPO_ROOT}/examples/minimal/Dockerfile" \
  "${REPO_ROOT}/examples/minimal"
docker push "${TEST_IMAGE}"

# Resolve digest
DIGEST=$(docker buildx imagetools inspect "${TEST_IMAGE}" \
  --raw | sha256sum | awk '{print $1}')
DIGEST_REF="localhost:5000/r4-admission-test@sha256:${DIGEST}"

# Sign (keyless via Sigstore)
COSIGN_EXPERIMENTAL=1 cosign sign --yes "${DIGEST_REF}"

# SBOM + attestation
syft "${DIGEST_REF}" -o cyclonedx-json > /tmp/sbom.json
COSIGN_EXPERIMENTAL=1 cosign attest --yes \
  --predicate /tmp/sbom.json --type cyclonedx "${DIGEST_REF}"
```

### Step 5 — Admission test 1 — UNSIGNED image MUST be rejected

```bash
UNSIGNED=localhost:5000/r4-admission-test:unsigned
docker tag "${TEST_IMAGE}" "${UNSIGNED}"
docker push "${UNSIGNED}"  # No cosign sign; no SBOM.

cat > /tmp/unsigned-pod.yaml <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: r4-unsigned-pod
  namespace: default
spec:
  containers:
  - name: app
    image: ${UNSIGNED}
EOF

kubectl apply -f /tmp/unsigned-pod.yaml 2>&1 | tee /tmp/admission-1.log
# Expected: error from server (UnsignedImage) — admission webhook denied
# the request: image is not signed by the trusted issuer.
```

Capture `admission-1.log` as evidence.

### Step 6 — Admission test 2 — Image WITHOUT SBOM MUST be rejected

```bash
NO_SBOM=localhost:5000/r4-admission-test:no-sbom
docker tag "${TEST_IMAGE}" "${NO_SBOM}"
docker push "${NO_SBOM}"
COSIGN_EXPERIMENTAL=1 cosign sign --yes "${NO_SBOM}"  # signed but NO attestation

cat > /tmp/no-sbom-pod.yaml <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: r4-no-sbom-pod
  namespace: default
spec:
  containers:
  - name: app
    image: ${NO_SBOM}
EOF

kubectl apply -f /tmp/no-sbom-pod.yaml 2>&1 | tee /tmp/admission-2.log
# Expected: admission webhook rejects (no CycloneDX attestation found).
```

### Step 7 — Admission test 3 — properly signed + attested MUST be admitted

```bash
cat > /tmp/good-pod.yaml <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: r4-good-pod
  namespace: default
spec:
  containers:
  - name: app
    image: ${DIGEST_REF}
EOF

kubectl apply -f /tmp/good-pod.yaml 2>&1 | tee /tmp/admission-3.log
kubectl get pod r4-good-pod -o jsonpath='{.status.phase}'
# Expected: Pending → Running. NO admission rejection.
```

### Step 8 — Cleanup

```bash
kubectl delete pod -l app=r4-admission-test --ignore-not-found
kind delete cluster --name r4-kyverno
docker stop kind-registry && docker rm kind-registry
```

---

## Recording evidence

In `VALIDATION_LOG.md`, open a new Entry with:

- Date + operator (human GitHub identity).
- kind / Kyverno / Cosign / Syft versions.
- Image digests for the three test images.
- Last 30 lines of each `/tmp/admission-N.log` (truncated, no secret leakage).
- The `kubectl get pod` output for the good pod.

Cross-link the entry from `README.md` § "Production-ready scope" once
this runbook closes — the row "Security and supply chain" can then
upgrade from "Production-ready" to "Verified end-to-end".

---

## Acceptance criteria for closing R4 H7

- [ ] Step 5 produced an admission rejection for unsigned image (log captured).
- [ ] Step 6 produced an admission rejection for missing-SBOM image (log captured).
- [ ] Step 7 produced a successful admission for properly signed + attested image.
- [ ] All three logs recorded in `VALIDATION_LOG.md` under a new Entry.
- [ ] `AuditEntry` written to `ops/audit.jsonl` via `scripts/audit_record.py` with `mode=STOP`, `approver=<lead>`, `result=success`.

---

## Cadence

Re-run this runbook:

- After every change to `templates/k8s/policies/`.
- After every Kyverno major version bump.
- After every change to the deploy chain's signing or SBOM steps.
- Quarterly minimum.
