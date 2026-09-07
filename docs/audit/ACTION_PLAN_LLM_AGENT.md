# ACTION PLAN — Local Agentic LLM Framework (WhatsApp + Store Assistant + Maintenance Plane)

> **Authority**: ADR-028 (LLM-assist, 4 tiers), ADR-037 (dual-namespace
> retrieval separation — operational memory vs. pedagogical RAG),
> AGENTS.md (AUTO/CONSULT/STOP), official Gemma 4 guide.
> **This document is the ONLY active plan for the LLM plane** — it absorbs
> and replaces `ACTION_PLAN_ADR028.md` (now a stub that points here). The
> template's maintenance lanes live in the "MAINTENANCE PLANE" section.
> **Audience**: an executing LLM (may be less capable than the author) or a
> human. Each step includes an objective, exact files, code, verification, and
> acceptance criteria. **Do not improvise outside the steps: if a gate fails,
> stop and report.**
>
> **Last updated**: 2026-07-01 (**v3.2** — canonicalized **L-2b: pedagogical
> RAG**, the namespace-disjoint sibling of L-2, with mandatory enterprise
> separation from operational memory; see ADR-037 and agent-local ADR-008).
> v3.1: `agent-local` executed: refactored into a **reusable platform** `core/`
>
> + `usecases/<domain>/`, public repo, F1 routing gate **PASSED 20/20**, and
> **F2.0** (ExecutiveController + circuit breaker) done; see "Execution
> status" below. v3 base: survivors of the adversarial review R1–R10,
> `ARCH_REVIEW_LLM_AGENT.md` → ADDENDUM v3).

## Execution status (2026-06-15)

| Phase | Status | Evidence |
| --- | --- | --- |
| F0 — Runtime + bench | ✅ E4B router PASSES speed gate | `agent-local/bench/RESULTS.md` |
| F1 — Skeleton (read-only) | ✅ **COMPLETE** | `agent-local` repo, suite green |
| F1 — Routing gate | ✅ **PASSED 20/20** (intent) | `agent-local/usecases/tienda/evals` |
| F2.0 — ExecutiveController + circuit breaker | ✅ **COMPLETE** | `core/controller.py`, `core/circuit.py`, 29 tests |
| F2.1 — Tier 1 (12B) fallback | ⏸️ **DEFERRED BY DESIGN** | entry conditioned on telemetry (plan §F2.1) |
| F2.2 — Policies as versioned data + `decision_id` | ✅ **COMPLETE** | `policies/policy.yaml`, `core/policy.py`, `tests/test_policy.py` (12), ADR-003 |
| F2.3 — Cross-verification + bounded self-consistency | ✅ **COMPLETE** | `core/controller.py` (`verify`), `tests/test_verifier.py` (7), ADR-004 |
| F2.4 — Tier 3 (31B) | ⏸️ **DEFERRED BY DESIGN** | conditional download (plan §F2.4) |
| F2.5 — The 10 eval sets | ✅ **CREATED** (offline gate) | `usecases/tienda/evals/sets/01..10`, `tests/test_eval_sets.py` — behavioral scoring pending on models |
| F3 — Decision telemetry + shadow mode | ✅ **COMPLETE** | `core/telemetry.py`, `TelemetryEntry`, `tests/test_telemetry.py` (9), ADR-005 |
| F4 — QLoRA | ⏸️ **GATE not reached (by design)** | requires ≥4 weeks of logs + stable evals (plan §F4) |

> **Frontier reached**: every phase that is *actionable without hardware/data*
> is done (77 tests green). What remains is blocked **by design**, not by the
> agent: F2.1/F2.4 (entry conditioned on telemetry / 31B download), behavioral
> scoring of the 10 sets (needs the tiers running), and F4 (≥4 weeks of logs).
> These unblock after the RAM upgrade.

### How to resume (resumption checklist)

> This subsection exists so that **anyone** (human or LLM) can resume without
> rereading the entire plan. Status as of 2026-06-15.

**What's built and green (do not touch except via ADR-backed refactor):**

+ `core/` (business-agnostic engine): `config · schemas · router · tiers · tools ·
  retrieval · policy · agent · controller · telemetry · circuit`.
+ `usecases/tienda/` (example): `config.yaml · tools.py · prompts/ · grammars/ ·
  policies/policy.yaml · budgets.yaml · data/ · evals/sets/01..10`.
+ 8 ADRs in `agent-local/docs/decisions/` (001 platform · 002 infra · 003
  policy-as-data · 004 cross-verification · 005 telemetry · 006 tool
  capability contract · 007 structured tool-calling · 008 caller isolation —
  see this repo's ADR-037).
+ **77 tests** green; `flake8` + `mypy` clean; CI without models.

**Command to verify status at any time:**

```bash
cd ~/projects/agent-local && .venv/bin/pytest -q && \
  .venv/bin/flake8 core tests --max-line-length 120 --extend-ignore E203,W503 && \
  .venv/bin/mypy core app
```

**Next actions IN ORDER once the RAM upgrade arrives (≥32GB usable):**

1. **Bring up the tiers** (F0.2): E4B:8091, 26B:8093 (12B:8092 only if it
   enters via §F2.1). Verify with `bench/bench.sh`.
2. **Behavioral scoring of the 10 sets** (F2.5): run `evals/run.py` against
   the live tiers; publish the router's confusion matrix and reports in
   `evals/reports/`. Gate per tier (table §F2.5).
3. **Accumulate telemetry** (F3 already implemented): with real traffic,
   `ops/telemetry.jsonl` starts filling with the evidence that conditions
   F2.1/F2.4/F4.
4. **F2.1 decision** (12B entry): only if telemetry shows the 26B spends
   >25% of its time on "medium" tasks (inverted burden of proof).
5. **F2.4 decision** (31B download): only if set 10 fails with 26B-verified.
6. **F4 (QLoRA)**: NOT before ≥4 weeks of logs + stable evals + a new ADR.

**Where to look first if something fails**: `bench/RESULTS.md` (model
speed/quality), `evals/reports/` (behavioral regression), `ops/telemetry.jsonl`
(per-request decisions). The 0→100 pedagogical guide lives in the adopter's
own private pedagogical/documentation corpus (out of scope for this public
repo).

**Key architectural change (agent's ADR-001)**: `agent-local` stopped being
a single app and is now a **reusable platform**: the critical logic (loop,
policy gate, objective escalation, grammar-constrained routing) lives in
`core/` (business-agnostic) and each domain is a `usecases/<name>/` (config

+ tools + prompts + evals), **never a fork of `core/`**. Consumed via
`from core import load_agent` or over HTTP. The store assistant is the
example use case (`usecases/tienda/`).

**Infra (agent's ADR-002)**: Docker + docker-compose for now (no models in the
image); K8s/Terraform deferred until model topology and volume are decided;
reuse of template modules where applicable.

**Public repo**: <https://github.com/DuqueOM/agent-local> (Apache-2.0, tests+lint
CI without models; docs in English).

### v3 decisions (adversarial review — executable summary)

| Decision | Status | Where it lands |
| --- | --- | --- |
| Two layers + **durable-state-as-data** (`sagas` table in SQLite; no Temporal) | adopted | F1.6 |
| **ExecutiveController**: `admit/execute/release` facade, pure-middleware interior, ≤250 LOC, in-memory circuit breaker | adopted | F2.0 |
| Deterministic pre-router chain (normalizer → alias → taxonomy → BM25) | adopted | F1.5 |
| Embedder + **semantic cache**: DEFERRED — trigger: ≥30% near-dups in logs (measurable offline); if it lands, it caches the ROUTE, never the response | trigger | F3 |
| **Startup without 12B** (router skips 0→2); enters only when telemetry demands it | adopted | F0/F2.1 |
| Cloud judge allowed ONLY in maintenance lanes with no PII; customer-facing high-stakes = local judge | adopted | Maint. plane |
| **Conditional reflect** (only on tool-fail or `risk≥medium`); K=3 only in ASYNCHRONOUS high-stakes flows and nightly evals | adopted | F1.6/F2.3 |
| Static `budgets.yaml` per intent + **daily cloud cap** + `max_reflections: 1`; adaptive rejected (revisit with 4 weeks of P95) | adopted | F1.6 |
| `policies/*.yaml` + `decision_id` + **policy-change-requires-test** (set 06) | adopted | F2.2 |
| **Mandatory telemetry** (a lane without events fails the validator) with OTel-compatible naming (`trace_id`…) | adopted | F1–F3 |
| Flywheel governance: PII redaction at write time, quarantine + human review, per-record provenance, 30-day raw retention | schema now | F3/F4 |
| n8n: deferred track (trigger: ≥2 real SaaS integrations); core stays code-first | trigger | P3 |

---

## 0. Fixed context (do not change without an ADR)

| Resource | Value |
| --- | --- |
| Machine | ASUS TUF Gaming F16 (FX608JPR) · i7-14650HX (16C/24T) · WSL2 Ubuntu-24.04 |
| GPU / VRAM | RTX 5070 **Laptop**, **8GB VRAM — soldered, fixed forever** (hard ceiling) |
| RAM today | **2× 8GB DDR5-5600 SODIMM, both slots full, dual-channel (~90 GB/s)** — no free slot; any upgrade is a *replacement* |
| RAM ceiling | **64GB (2×32) = maximum declared/reliable configuration.** 96GB (2×48) = beyond declared spec, an unguaranteed bet on this HX chip. 128GB (2×64) = unsupported, do not bet on it |
| Runtime | llama.cpp (`llama-server`, OpenAI-compatible API) |
| Models on disk (`~/ml-models/`) | `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf` (4.0G) · `gemma-4-12b-it-qat-q4_0.gguf` (6.5G) · `gemma-4-26B_q4_0-it.gguf` (14G) |
| Repos | `~/projects/template_MLOps` (maintenance plane) · `~/projects/agent-local` (**reusable LLM platform**, public repo; the store assistant is `usecases/tienda/`) |

> ⚠️ **2026-06-15 correction**: the "48GB" figure from earlier versions was a
> premise error (it was assumed "16GB + one free slot → +32"). Reality: 2 full
> slots at 8GB each; the upgrade replaces both. Recommended target **64GB
> (2×32) dual-channel** — unblocks all pending phases with headroom for the
> 26B Q4_K_M at 16–32k context. See §0.5 (RAM↔model upgrade path).

### 0.5 RAM ↔ model upgrade path (what each RAM tier unlocks)

VRAM (8GB) is the hard, immovable ceiling; fast RAM is the lever. The speed of
a MoE model is governed by **active parameters**, not total parameters
(`tok/s ≈ ~60 GB/s effective / (active × bytes_per_param)`).

| RAM | Viable "primary" model | "Judge" model (tolerates latency) | Notes |
| --- | --- | --- | --- |
| 16GB (today) | E4B / 12B Q4 | — | the 26B-A4B doesn't fit comfortably |
| **64GB (2×32, target)** | **Qwen3-30B-A3B** (3B active, Q4 ~17GB) or 26B-A4B (4B active, ~15GB) | Gemma-4 31B Q4 (~17GB) **or** gpt-oss-120B **Q3** (~48GB, 5B active, batch-only, monopolizes RAM) | sweet spot; a single large resident model at a time |
| 96GB (2×48, bet) | same + huge context | **gpt-oss-120B Q4** (~60GB, 5B active, ~10-18 tok/s) | the only RAM tier that fits gpt-oss-120B Q4 comfortably |

**Role-selection rule** (decided by eval, not intuition): router = small and
structured (fits in VRAM); primary = **low-active-parameter MoE** that fits in
RAM; judge = the largest that fits, tolerates slowness. Candidates to evaluate
after the upgrade: **Qwen3-30B-A3B** as primary (a real upgrade over 26B-A4B);
gpt-oss-120B (Q3 at 64GB / Q4 at 96GB) as judge. Mixtral 8×7B / 8×22B
**ruled out**: high active parameters (13B/39B) → slow on bandwidth-limited
hardware, and outperformed by fine-grained MoEs.

### 0.6 Models as configuration (swappability — design rule)

**The model behind each tier is CONFIGURATION, never code.** Swapping a model
(a specific one or the whole family) must be a YAML edit + re-validation, zero
code changes. This is already possible because the client is OpenAI-compatible
and routing uses GBNF (model-agnostic); this rule formalizes it:

1. **`models.yaml` registry**: each entry = `{tier, model_id, gguf_path,
   port, quant, context, role, min_ram_gb, expected_tok_s}`. The tier
   references a `model_id`, never a hardcoded path.
2. **Capability validation**: the controller checks `min_ram_gb` and available
   VRAM BEFORE loading — if the model doesn't fit, it fails clean, it does not
   swap silently.
3. **Eval gates per ROLE, not per model** (this is already the design, §F2.5):
   any model entering a tier MUST re-pass that tier's eval sets. This is what
   makes the swap **safe** instead of a bet.
4. **Swap runbook**: download GGUF → register in `models.yaml` →
   `llama-bench` (speed gate) → tier eval set (quality gate) → if both are
   green, promote; if not, revert the `model_id`. One entry in
   `bench/RESULTS.md` per swap.

✅ **Cost of doing this now vs. later**: doing it during construction is
trivial (one YAML + one loader); retrofitting it after hardcoding paths is
painful. It is also the "engineered for change" interview signal: the system
is not married to Gemma — it is married to *contracts* (grammar-constrained
JSON, per-tier eval), and the models underneath them are interchangeable.

**Non-negotiable principles** (copied from the framework — verify them on
every PR):

1. No fine-tuning at this stage: structured routing + prompts + retrieval.
2. The model never mutates critical state without policy validation.
3. Every lane needs an eval harness BEFORE raising autonomy.
4. The simplest loop that works.
5. Inventory/pricing/stock NEVER in the model's memory — always a live API.
6. Local first; cloud only as an explicit overflow.

### 0.1 Tier table (reconciled with the artifacts on disk)

| Tier | Role | Target model | Artifact TODAY | Action |
| --- | --- | --- | --- | --- |
| 0 | Router/guardrail | E4B Q4_K_M | E4B QAT Q4_K_XL ✅ | bench the local one first |
| 1 | Medium reasoning | 12B Q4_K_M | 12B QAT Q4_0 ✅ | bench the local one first |
| 2 | Primary assistant | 26B-A4B Q4_K_M | 26B QAT Q4_0 ✅ | bench the local one first |
| 3 | Verifier/escalation | 31B Q4_K_M | ❌ not downloaded | **deferred** — only if Gate-3 requires it |

> ⚠️ **On the 31B**: on this hardware it delivers ~2–4 tok/s (dense,
> bandwidth-limited). It is INFEASIBLE as an interactive assistant but VIABLE
> as a latency-tolerant verifier (final verification, nightly evals, escalated
> cases without a chat SLA). Do not download it before step F2.4. When it's
> time: official `ggml-org` GGUF Q4_K_M repo (~17GB).
>
> 📝 **Quantization policy**: the framework calls for Q4_K_M. We already have
> QAT-Q4_0/Q4_K_XL downloaded. Rule: bench the local one first (step F0.3);
> download the `ggml-org` Q4_K_M ONLY if the local one fails its gate on
> quality (not on speed). Document any change in `bench/RESULTS.md`.

### 0.2 Role contract — ARCHITECTURE RULE (not an informational table)

Each model has ONE fixed role with a contract. Violating the contract is an
architecture bug, not a preference:

| Model | Contractual role | CAN | CANNOT |
| --- | --- | --- | --- |
| **E4B** | Router / guardrail | classify, normalize aliases, emit routing JSON with confidence | draft customer-facing replies; approve anything |
| **12B** | Medium-reasoning buffer | clarifications, drafts another tier will verify, E4B→26B fallback | be the final destination for commercial or high-stakes cases |
| **26B-A4B** | Primary assistant | customer conversation, semantic matching, tool planning, multi-turn | approve its own policy violations; touch state without a policy gate |
| **31B** | **JUDGE** (not a daily worker) | final verification, escalated high-stakes cases, audits, nightly evals | serve interactive traffic; be a fallback out of routing laziness |

Clauses:

+ **12B clause**: stays in the architecture ONLY as long as per-tier evals
  demonstrate it reduces unnecessary escalations to the 26B and improves
  clarifications. If two consecutive eval cycles fail to justify it, it is
  retired and the router skips 0→2. It earns its place through measured
  utility, not "because it's there."
+ **Judge clause**: the 31B never receives a task that a lower tier has not
  already attempted, except for `risk=high` or final verification. Its
  compute time is expensive: every invocation is logged with its
  justification.
+ Whoever drafts is NEVER the one who approves: verification of a tier-N
  response is done by the deterministic policy layer + (if `risk≥medium`) a
  critique pass at tier N or N+1 with a verifier prompt — never the same
  prompt that generated the response.

---

## PHASE 0 — Runtime and bake-off (prerequisite for everything)

### F0.1 Install llama.cpp with CUDA support

```bash
cd ~/tools && git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j "$(nproc)" --target llama-server llama-bench llama-cli
# Verification:
./build/bin/llama-server --version && ./build/bin/llama-bench --help >/dev/null && echo OK
```

**Acceptance**: prints a version and `OK`. If CUDA fails, compile without
`-DGGML_CUDA=ON` and note "CPU-only" in `bench/RESULTS.md` (speed gates drop
30%).

### F0.2 Launch each model as a server (fixed ports)

```bash
# Tier 0 (E4B) — port 8091
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
  --port 8091 -ngl 99 -c 8192 --host 127.0.0.1 &
# Tier 1 (12B) — port 8092  (-ngl partial: ~20 layers fit in 8GB VRAM)
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-12b-it-qat-q4_0.gguf \
  --port 8092 -ngl 20 -c 16384 --host 127.0.0.1 &
# Tier 2 (26B-A4B) — port 8093 (MoE: experts on CPU, attention on GPU)
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-26B_q4_0-it.gguf \
  --port 8093 -ngl 99 --override-tensor "ffn_.*_exps.=CPU" -c 16384 --host 127.0.0.1 &
```

> 💡 Only ONE large server at a time in local "production" (RAM). For the
> bench, sequential is fine: bring up → measure → kill (`pkill -f
> llama-server`).

### F0.3 Benchmark script and gates

Create `~/projects/agent-local/bench/bench.sh`:

```bash
#!/usr/bin/env bash
# Usage: ./bench.sh <port> <name>
set -euo pipefail
PORT=$1; NAME=$2
PROMPT='Clasifica la intención y responde SOLO JSON: {"intent":"...","tier":0}. Mensaje: "tienen coca de 600 fria?"'
START=$(date +%s.%N)
RESP=$(curl -s http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"max_tokens\":120,\"temperature\":0}")
END=$(date +%s.%N)
TOKENS=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["usage"]["completion_tokens"])')
echo "$NAME: $(echo "$TOKENS/($END-$START)" | bc -l | cut -c1-5) tok/s" | tee -a RESULTS.md
```

**Gates (log them in `bench/RESULTS.md`; if one fails, STOP and report):**

| Tier | Speed gate | Quality gate |
| --- | --- | --- |
| E4B | ≥ 25 tok/s | 18/20 on the routing set (F1.6) |
| 12B | ≥ 10 tok/s | beats E4B on the clarification set |
| 26B | ≥ 8 tok/s @16k | beats 12B on the semantic-matching set |

---

## PHASE 1 — Agent skeleton (read-only, E4B + 26B)

### F1.1 Create the repo

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # ver pyproject.toml
```

> **NOTE v3.1 (implemented, agent's ADR-001)**: the original target structure
> (everything under `app/`) evolved into a **reusable platform**. The critical
> logic lives in `core/` (business-agnostic) and each domain is a
> `usecases/<name>/`. The code blocks in F1.2–F1.x below remain the
> **conceptual reference** for each contract/station; their actual location is
> `core/` (engine) and `usecases/tienda/` (config + tools for the example).

Actual structure (`agent-local` repo):

```text
agent-local/
├── core/                  # business-agnostic ENGINE (single source of truth)
│   ├── config.py          #   UsecaseConfig: loads prompts/grammar/budgets/policy
│   ├── schemas.py         #   Pydantic contracts (intent = str; grammar fixes the set)
│   ├── router.py          #   Tier 0 → strict JSON (GBNF) + allowed_intents validation
│   ├── tiers.py           #   per-tier clients (endpoints injected from config)
│   ├── tools.py           #   ToolRegistry (the APP executes; namespaced per use-case)
│   ├── retrieval.py       #   BM25 + semantic_retrieval factory
│   ├── policy.py          #   deterministic gate (rules = data: PolicyRules)
│   ├── agent.py           #   7-station loop (prompts injected from config)
│   └── __init__.py        #   load_agent(name)
├── usecases/tienda/       # example USE CASE (store assistant)
│   ├── config.yaml        #   endpoints, allowed_intents, policy rules, prompts
│   ├── tools.py           #   build_registry(config) -> ToolRegistry
│   ├── prompts/ grammars/ data/ policies/ budgets.yaml evals/sets/
│   └── __init__.py        #   exposes build_registry
├── core/telemetry.py      #   F3: TelemetrySink (JSONL per request, PII redacted)
├── core/controller.py     #   F2.0: ExecutiveController + circuit breaker + verifier
├── app/main.py            # webhook/transport FastAPI; loads use case via AGENT_USECASE
├── tests/ bench/ evals/run.py   # 77 tests green (flake8 + mypy clean)
├── Dockerfile docker-compose.yml pyproject.toml
└── docs/decisions/        # ADR-001 platform · 002 calibrated infra · 003 policy-as-data
                           #   · 004 cross-verification · 005 decision telemetry
                           #   · 006 capability contract · 007 structured tool-calling
                           #   · 008 caller isolation (retrieval, see ADR-037)
```

**Creating a new domain** = a new `usecases/<name>/` folder (config + tools +
prompts + evals), **never** a fork of `core/`.

### F1.2 Contracts (`app/schemas.py`) — write FIRST

```python
from pydantic import BaseModel, Field
from typing import Literal

class Route(BaseModel):
    intent: Literal["product_lookup", "order_create", "order_status",
                    "smalltalk", "complaint", "policy_question",
                    "maintenance_task", "unknown"]
    tier: Literal[0, 1, 2, 3]
    confidence: float = Field(ge=0.0, le=1.0)  # OBJECTIVE escalation, not heuristic
    risk: Literal["low", "medium", "high"]
    ambiguity: Literal["low", "medium", "high"]
    tool_needed: bool
    finality: Literal["answer", "clarify", "escalate"]
    expected_followup: bool

class RequestBudget(BaseModel):
    """Per-request budget — prevents pretty-but-expensive loops.
    v3: per-intent values live in budgets.yaml (versioned); this
    model only types them. Adaptive budgets: rejected until we have
    >=4 weeks of real P95 data."""
    max_iterations: int = 4
    max_tool_calls: int = 6
    max_reflections: int = 1            # v3: reflect is conditional and bounded
    latency_budget_ms: int = 8000       # channel SLA (WhatsApp ~= 8s)
    can_escalate_t3: bool = False       # the 31B requires explicit permission
    # daily cloud cap: global counter in the controller, not per request

class ToolCall(BaseModel):
    tool: str
    args: dict

class Observation(BaseModel):
    tool: str
    ok: bool
    data: dict
    error: str | None = None

class Verdict(BaseModel):
    approved: bool
    violations: list[str] = Field(default_factory=list)
    escalate_to_tier: int | None = None
```

### F1.3 Tier 0 router with grammar (JSON output that cannot be broken)

`grammars/route.gbnf` (llama.cpp GBNF — forces the JSON shape):

```text
root   ::= "{" ws "\"intent\"" ws ":" ws intent "," ws "\"tier\"" ws ":" ws tier "," ws "\"confidence\"" ws ":" ws conf "," ws "\"risk\"" ws ":" ws lvl "," ws "\"ambiguity\"" ws ":" ws lvl "," ws "\"tool_needed\"" ws ":" ws bool "," ws "\"finality\"" ws ":" ws fin "," ws "\"expected_followup\"" ws ":" ws bool ws "}"
intent ::= "\"product_lookup\"" | "\"order_create\"" | "\"order_status\"" | "\"smalltalk\"" | "\"complaint\"" | "\"policy_question\"" | "\"maintenance_task\"" | "\"unknown\""
tier   ::= "0" | "1" | "2" | "3"
conf   ::= "0." [0-9] [0-9]? | "1.0"
lvl    ::= "\"low\"" | "\"medium\"" | "\"high\""
fin    ::= "\"answer\"" | "\"clarify\"" | "\"escalate\""
bool   ::= "true" | "false"
ws     ::= [ \t\n]*
```

`app/router.py`:

```python
import httpx, json
from .schemas import Route

ROUTER_URL = "http://127.0.0.1:8091/v1/chat/completions"
SYSTEM = open("prompts/router.md").read()
GRAMMAR = open("grammars/route.gbnf").read()

RULES = """Reglas de tier (aplícalas tras clasificar):
1. simple/determinista/clasificación -> tier 0
2. razonamiento moderado sin planning -> tier 1
3. cara al cliente, semántico, comercial o multi-tool -> tier 2
4. alto riesgo, ambiguo, o afecta pedidos/dinero/confianza -> tier 3
5. NUNCA saltes directo a 3 salvo risk=high o ambiguity=high.
confidence: tu certeza en ESTA clasificación (0.00-1.0)."""

# OBJECTIVE escalation (in loop.py, not in the prompt):
#   confidence < 0.70           -> bump a tier before planning
#   verification rejects        -> bump a tier (once only)
#   tier==3 required but budget.can_escalate_t3==False
#                               -> safe partial answer + flag to a human

def route(message: str) -> Route:
    r = httpx.post(ROUTER_URL, json={
        "messages": [{"role": "system", "content": SYSTEM + "\n" + RULES},
                     {"role": "user", "content": message}],
        "temperature": 0, "max_tokens": 160, "grammar": GRAMMAR,
    }, timeout=30)
    return Route.model_validate_json(r.json()["choices"][0]["message"]["content"])
```

`prompts/router.md` (versioned in git — NOT inline in code):

```markdown
Eres el router de un asistente de tienda por WhatsApp. Clasifica el mensaje
del cliente y produce SOLO el JSON pedido. Normaliza ortografía y alias
mentalmente ("coca"→producto familia Coca-Cola) pero NO resuelvas el pedido.
risk=high si el mensaje implica dinero, pedido o promesa. ambiguity=high si
falta talla/cantidad/variante para actuar.
```

### F1.4 Tools (the app executes, the model only names them)

`app/tools.py`:

```python
from .schemas import Observation

# Phase 1: read-only stubs against fixtures. Phase 2: real APIs.
REGISTRY = {}

def tool(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco

@tool("inventory_lookup")
def inventory_lookup(product_id: str) -> Observation:
    import json
    db = json.load(open("retrieval/data/inventory_fixture.json"))
    item = db.get(product_id)
    return Observation(tool="inventory_lookup", ok=item is not None,
                       data=item or {}, error=None if item else "not_found")

@tool("alias_lookup")
def alias_lookup(text: str) -> Observation:
    import json
    aliases = json.load(open("retrieval/data/aliases.json"))
    hits = [pid for pid, names in aliases.items()
            if any(a in text.lower() for a in names)]
    return Observation(tool="alias_lookup", ok=bool(hits), data={"candidates": hits})

# Same pattern: pricing_lookup, order_create (Phase 1: ALWAYS dry_run=True),
# order_status, crm_lookup, policy_check, semantic_retrieval (BM25, F1.5).

def run(call):  # single execution + logging chokepoint
    fn = REGISTRY.get(call.tool)
    if fn is None:
        return Observation(tool=call.tool, ok=False, data={}, error="unknown_tool")
    return fn(**call.args)
```

> ⚠️ **`order_create` in Phase 1 is ALWAYS `dry_run=True`.** The real flag is
> enabled by the policy layer in Phase 2, never by the model.

### F1.5 File-based retrieval (before any vector store)

`retrieval/data/aliases.json` (seed — grows with the logs):

```json
{
  "SKU-COCA-600": ["coca", "cocacola", "coca cola", "coca de 600", "refresco coca"],
  "SKU-FRIJOL-NEGRO-1KG": ["frijol", "frijol negro", "frijol americano", "frijoles"]
}
```

BM25 over files (`app/retrieval.py`): indexes `retrieval/data/*.md` (store
policies, promotions, objection-handling templates) with `rank-bm25`; expose
`semantic_retrieval(query, k=3)` as a tool. **No stock/pricing here.**

### F1.6 Formal loop (`app/loop.py`) and webhook (`app/main.py`)

The full loop has 7 stations — in Phase 1, `reflect` and `critic` can be the
same model with different prompts; in Phase 2, `critic` moves up a tier:

```text
route → plan → tools → observe → reflect → critic → policy → finalize
  E4B    tierN   app     app      tierN    tierN/N+1  deterministic  tierN
```

+ **plan**: at most `budget.max_tool_calls` tools, named explicitly.
+ **observe**: tool results injected in a compact schema.
+ **reflect**: the model checks its plan against the observations — is a
  datum missing? did a tool contradict an assumption? (1 pass, no exposed
  chain-of-thought).
+ **critic**: a verifier prompt (NOT the generation one): consistency with
  live data, clarity, zero hallucinated inventory, zero illegal promises.
+ **policy**: deterministic gate (F2.2) — **invariant: NO final response goes
  out without passing `product_exists`, `stock_confirmed`, `price_confirmed`,
  `no_overpromise`, and `tone_brand`**. No exceptions, not even smalltalk that
  mentions products.
+ **finalize**: customer-facing format, short and commercial.

Hard stop-conditions (from `RequestBudget`): `max_iterations`; if
`finality=clarify` twice in a row → ONE direct question to the user; if it
oscillates → a safe template; if `latency_budget_ms` is exhausted → a safe
partial response + flag.

**Adaptive depth (v3)**: `reflect` runs ONLY if (a) a tool failed or
contradicted the plan, or (b) `risk≥medium`. Smalltalk and clean lookups go
`plan→tools→policy→final` — the extra model pass isn't paid for where it adds
no value.

FastAPI webhook: `POST /webhook/whatsapp` validates the signature (token in
env `WA_VERIFY_TOKEN`), enqueues the message, responds 200 immediately,
processes asynchronously, and replies via the WhatsApp Business API (env
`WA_TOKEN`, `WA_PHONE_ID`). In Phase 1 you can test EVERYTHING with
`POST /dev/message {"text": "..."}` without WhatsApp.

**Queue and durable state (v3)** — a single SQLite (`app/state.db`, WAL):

+ `queue(conv_id, msg, status, ts)` table — one worker per conversation
  (guaranteed order); a crash does NOT lose messages.
+ `sagas(saga_id, tipo, paso, estado, deadline, retries)` table — the
  *durable-state-as-data* pattern for multi-day flows (order → confirmation →
  follow-up) with a periodic sweep by the worker. **No Temporal**: that is an
  ADR-trigger (≥3 saga types or distributed exactly-once).
+ `budgets.yaml`: per-intent budget (the schema defaults are the fallback);
  daily cloud cap as a counter in the controller.

### F1.7 Routing set + tests (phase gate)

`evals/sets/01_intent.jsonl` — 20 minimum cases (5 product_lookup with alias
and spelling mistakes, 3 order_create, 3 complaint, 3 smalltalk, 3 policy, 3
ambiguous cases that MUST come out as `finality=clarify`). Runner
`evals/run.py`: reads JSONL, calls `route()`, compares `intent/tier/finality`,
prints accuracy, and saves `evals/reports/<date>_intent.json`.

**Phase 1 acceptance**: router ≥ 18/20; the end-to-end loop answers a
`product_lookup` with alias + stock fixture without hallucinating inventory;
`pytest tests/` green; everything read-only.

---

## PHASE 2 — Controller, intermediate tiers, verifier, policies, and evals

### F2.0 ExecutiveController (`app/controller.py`) — v3

Single facade through which EVERY request passes; interior of **pure
middlewares** (`(ctx) -> ctx`, testable in isolation). Hard cap: ≤250 LOC or
it gets split.

```python
class ExecutiveController:
    def admit(self, msg) -> Ctx:      # normalize → alias/BM25 → route(E4B) → budget
    def execute(self, ctx) -> Ctx:    # adaptive loop; retries ONLY for idempotent
                                      # tools; per-tier circuit breaker
                                      # (3 failures → degrade a tier + templates,
                                      # half-open at 60s; state kept IN MEMORY)
    def release(self, ctx) -> Final:  # policy gate → telemetry → finalize
```

What does NOT go here: prompts, business logic, domain knowledge.

### F2.1 Tier 1 (12B) as an intermediate fallback — CONDITIONAL ENTRY (v3)

**Startup WITHOUT 12B**: the router skips 0→2. The artifact stays on disk; the
12B enters only once telemetry shows the 26B spends >25% of its time on tasks
that set 07 classifies as "medium" (inverted burden of proof). If it enters:
`app/tiers.py` client per port; escalates if the tier-N verifier rejects or
`confidence<threshold`, re-runs at N+1 (once only).

### F2.2 Policy layer (`app/policy.py`) — deterministic gate, NOT an LLM

```python
CHECKS = [
    ("product_exists",  lambda ctx: ctx.product is not None),
    ("stock_confirmed", lambda ctx: ctx.stock_checked_live),
    ("price_confirmed", lambda ctx: ctx.price_checked_live),
    ("order_rules",     lambda ctx: ctx.order is None or ctx.order.valid()),
    ("no_overpromise",  lambda ctx: not ctx.reply_mentions_unavailable_promise()),
    ("tone_brand",      lambda ctx: ctx.reply_passes_tone_lint()),
]
def check(ctx) -> Verdict:
    fails = [n for n, f in CHECKS if not f(ctx)]
    return Verdict(approved=not fails, violations=fails,
                   escalate_to_tier=3 if fails else None)
```

On failure: escalate to Tier 3 → or ask for clarification → or a safe partial
response (in that order). The model NEVER approves its own violation.

**Policies as data (v3)**: thresholds, tools allowed per intent, maximum
amounts, prohibited commitments, and tone per channel live in
`policies/*.yaml` (versioned — the PR diff IS the compliance audit trail).
Every verdict emits `{policy_version, rules_fired, decision_id}` to telemetry.
**policy-change-requires-test rule**: no YAML change merges without its case
in set 06 that fails without the change. OPA/Rego: rejected at this scale
(revisit only with multi-tenant).

### F2.3 Critique pass (cross-verification)

For `risk=medium|high`: the 26B's response passes through a verifier prompt
("is it consistent with the tool data? does it promise something unconfirmed?
is it clear to the customer?") on the SAME 26B (Phase 2a) and on the 31B once
it exists (Phase 2b).

**Self-consistency (v3, bounded)**: K=3 with voting ONLY in ASYNCHRONOUS
high-stakes flows (order confirmation, 15–20s acceptable) and in nightly
evals. In interactive mode, 3 passes of the 26B blow the 8s budget: a single
pass + judge.

### F2.4 Tier 3 (31B) — conditional download

Download `ggml-org` Q4_K_M (~17GB) ONLY if: (a) the high-stakes eval (set 10)
fails with 26B-verified, or (b) nightly evals justify it. Use it exclusively
for: final verification, nightly evals, escalations with no SLA.

### F2.5 The 10 evaluation sets

In `evals/sets/`: `01_intent`, `02_alias_match`, `03_oos_substitution`,
`04_upsell`, `05_objections`, `06_policy_violation`, `07_ambiguity`,
`08_multiturn`, `09_tool_failure`, `10_high_stakes` (20–40 cases each, JSONL:
`{"input":..., "expected":..., "must_escalate":bool, "must_call_tools":[...]}`).
The runner measures: accuracy, escalation correctness, tool correctness,
hallucination rate (mention of stock/price not present in observations),
latency, policy adherence. Reports versioned in `evals/reports/`.

**v3 — two additional instruments**:

+ **Frozen golden set** (`evals/golden/`, 50 cases, NEVER edited or grown):
  measures long-term system drift; the live sets measure coverage. Editing
  the golden set invalidates the historical series.
+ **Replay against real traffic**: `evals/replay.py --from logs/<day>.jsonl
  --against <prompt|policy>` — every prompt/policy change is tested against
  yesterday's traffic BEFORE it sees today's.
+ The router's confusion matrix is published every cycle (not just accuracy):
  over-escalating costs latency; under-escalating costs quality.

**Graduation gates PER TIER** (mandatory before promoting any prompt, model,
or rule change — the global eval alone is not enough):

| Tier | Wins in ITS role if... | Set that measures it |
| --- | --- | --- |
| E4B | routing precision ≥ threshold and calibrated confidence (high confidence ⇒ high precision) | 01_intent |
| 12B | reduces unnecessary escalations to the 26B and improves clarifications vs. E4B | 07_ambiguity + 01 |
| 26B | beats the 12B on real semantic/commercial matching | 02, 03, 04, 05, 08 |
| 31B | catches violations the 26B-verified let through, in high-stakes cases | 06, 10 |

Rules: no lane gains autonomy without a green regression
(`pytest -m regression`) · a tier that loses in its own role two cycles in a
row gets reconfigured or retired (12B clause, §0.2) · the 31B justifies its
cost/latency only in selected cases — if the eval shows the 26B-verified ties
it, the 31B is kept solely for nightly evals.

---

## PHASE 3 — Observability and continuous improvement

1. **Decision telemetry** (JSONL per request, PII redacted) — mandatory
   fields, because without this, refinement is guesswork:

   ```json
   {"ts": "...", "trace_id": "...", "route": {...}, "tier_final": 2,
    "confidence": 0.84, "escalated": false, "escalation_reason": null,
    "tools": ["alias_lookup", "inventory_lookup"], "tool_failures": [],
    "policy_verdict": {"approved": true, "violations": [],
                       "policy_version": "...", "decision_id": "..."},
    "critic_verdict": "approved", "latency_ms": {"route": 320, "total": 4100},
    "cost": {"tokens_by_tier": {"0": 160, "2": 840}},
    "budget_exhausted": false, "outcome": "answered",
    "provenance": {"source": "prod", "reviewer": null, "quarantine": true}}
   ```

   **v3 — three hard rules**: (1) telemetry is a CONTRACT, not a best
   practice — a lane that does not emit the schema fails the validator (the
   agentic world's prediction-logger, D-20); (2) naming aligned to OTel
   semconv (`trace_id` propagated to tools and tiers) so that adopting OTel
   later is a transport swap (trigger: team >1 or >1 host); (3) PII redacted
   AT WRITE TIME, never afterward.

   This is how prompts, verification prompts, and escalation rules improve
   with data instead of intuition — and the `provenance` fields are the
   governed seed of the F4 flywheel: nothing leaves quarantine into a dataset
   without batched human review; raw data is retained 30 days, curated data
   indefinitely; judge rejections generate the DPO pairs.
2. Weekly offline failure analysis → new cases added to the sets (the eval
   set GROWS with production).
3. **Retrieval growth cycle** (before any LoRA): every week, customer terms
   that alias-lookup did NOT resolve go to review → new entries in
   `aliases.json` / category equivalences / regional variants, via PR.
   Retrieval matures with real traffic; the model memorizes nothing.
4. Prompt refinement ONLY with eval evidence (versioned diff in `prompts/`).
5. Synthetic generation of variants (regional aliases, spelling mistakes)
   using the local 26B — human review before entering the set.
6. Shadow mode: every routing decision is logged alongside "what the tier
   above would have done" on a 10% sample.

## PHASE 4 — QLoRA (strategic gate, NOT before)

Only with: ≥4 weeks of logs, stable evals, and a style/tone/policy pattern
that prompting cannot resolve. Train ONLY stable behavior (tone, format,
brand protocol). PROHIBITED to train on inventory, stock, or prices.
Requires a new ADR in the template.

---

## MAINTENANCE PLANE — ADR-028 lanes on the SAME stack

> Absorbed from `ACTION_PLAN_ADR028.md` (now a stub). The lanes reuse the
> tiers, the grammar-constrained client, and the eval harness from the
> earlier phases — this is a second consumer of the same runtime, not a
> different system.

### L-4 Docs-drift updater (first productive lane — cheap and verifiable)

The LLM is the *writer*, not the *detector*:

1. A deterministic Python extractor gathers code-visible facts (counts of
   rules/skills/workflows, overlay names, inventory tables).
2. A comparator flags doc claims that don't match — no LLM involved.
3. `E4B` drafts the PR body + doc diffs ONLY for the mismatches,
   JSON-constrained.
4. Opens a **CONSULT PR** via `gh`. A human merges.

Runtime: **the laptop is the runner** (weekly systemd timer in WSL) — zero CI
dependency, zero cloud cost. Admission eval: 10 synthetic drift cases seeded
(mutate a count, rename an overlay) → ≥9/10 detected with 0 false patches.

### L-2 Memory plane Phase 2 (= P2.4) — embeddings-free first

1. BM25 over existing artifacts: `ops/audit.jsonl`, `docs/incidents/`,
   `VALIDATION_LOG.md`, `releases/*.md`, drift reports.
2. `scripts/memory_query.py "<question>"` → top-k chunks → `E4B` summarizes
   **with mandatory file:line citations** — a response without a citation is
   discarded.
3. Eval: 20 historical questions with known answers; recall@5 ≥ 80% or the
   vector store is re-evaluated (not before).

### L-2b Pedagogical RAG — namespace-disjoint sibling of L-2 (ADR-037)

> **Canonical since v3.2.** Born from a natural question ("can we reuse the
> `agent-local` stack so newcomers can ask questions about the template?")
> that is dangerous without an explicit separation: mixing the pedagogical
> corpus with operational runbooks/evidence in the SAME index risks
> operational leakage toward a more exposed surface (a possible widget on the
> docs site). **ADR-037** formalizes the separation; this section executes it.

1. **Never the same script as L-2.** `scripts/pedagogy_query.py` (new) is an
   entry point separate from `scripts/memory_query.py` — never a
   `--namespace` flag on the same script. A flag can default wrong or be
   forgotten at a call site; two scripts force the caller to name the wrong
   one on purpose.
2. **Disjoint corpus, hardcoded, never parameterizable by request**: the
   adopter's own private pedagogical/documentation corpus (out of scope for
   this public repo), `docs/decisions/ADR-*.md` (prose only — context/
   decision/consequences read as pedagogical material, never as an
   operational log), `docs/TUTORIAL.md`, `docs/CCDS_MAPPING.md`, glossary.
   **Prohibited**: `ops/`, `docs/incidents/`, `VALIDATION_LOG.md`,
   `releases/*.md` — that is exclusively L-2/ADR-018.
3. **Its own index, never shared**: `pedagogy_query.py` builds its own
   in-process `BM25Index` — no object, file, or table is shared with the L-2
   index. The only thing the two scripts share is `agent-local`'s E4B
   endpoint (`http://127.0.0.1:8091/...`), safe to share precisely because
   the tier holds no state between requests (agent-local ADR-008) — sharing
   the tier is a hardware-cost decision, not a concession on separation.
4. **Citations with namespace validation (the runtime backstop)**: in
   addition to "no citation, no response" (already in force in L-2), a
   citation that does NOT resolve within the allow-list of the namespace that
   answered is discarded and generates an integrity event — it is never
   served. This is what turns "we designed it separate" into "we verify on
   every query that it stayed separate."
5. **Telemetry with mandatory `namespace`** (`"operational"|"pedagogical"`, a
   closed 2-value enum) on every line — auditable with
   `grep namespace ops/*.jsonl`.
6. **Dedicated CI gate**: `tests/test_retrieval_namespace_isolation.py` (new)
   verifies the two allow-lists never intersect and that neither resolves
   (via glob) to a file in the other's exclusive root.
7. **This is not a Phase of ADR-018.** The Operational Memory Plane has its
   own threat model (leaked CI tokens, secret redaction, tenancy) that
   pedagogical content does not have and must not pretend to have. This lane
   is its own, lighter, BM25-first mechanism — never a new `memory_type`
   inside ADR-018's `MemoryUnit`.

**L-2b acceptance**: `test_retrieval_namespace_isolation.py` green · a unit
test for "a citation outside its namespace is rejected and logged" · both
scripts emit `namespace` validated against the closed enum · the adopter's
private pedagogical corpus documentation describes the separation for a human
reader, not only in code.

**Status**: specified (this ADR + this section), NOT implemented — same as
L-2 itself, gated behind the same "P2 INTEGRATION" timeline (neither script
exists yet). See ADR-037 for the full record of alternatives considered and
consequences.

### L-3 Drift/incident triage

1. A joiner gathers: Prometheus signals (MCP), prediction-log slices, deploy
   history (`git log` + digests).
2. `26B-A4B` drafts the RCA in `report_schema.json` — a batch job, minutes of
   runtime acceptable.
3. The draft is attached to the issue. **The human owns the conclusion.**
4. Eval: replay of 3 historical incidents; hallucinated causality (asserting
   a cause absent from the evidence) = automatic failure → that subtask goes
   to cloud.

### L-1 CI self-healing Phase 2 — local models stay OUT of the CI path

Two reasons, both about security (not capability):

1. GitHub's runners cannot reach the laptop.
2. A self-hosted runner on a personal laptop against a public repo is a known
   attack vector (fork PRs execute on your machine) — **rejected**.

In CI: heuristic classification first, cheap-tier cloud where needed; patch
generation in cloud, CONSULT, per `model_routing_policy.yaml` (local tiers are
registered there BELOW the cheapest cloud tier; ADR-010's escalation-only
discipline does not change — a local model may flag, never approve). The
local tiers help *offline*: a nightly job replays the day's CI failures
against the classifier prompt to grow the labeled corpus (feeds the
fine-tuning review triggers, >10k labeled events).

### Plane risks (inherited and still current)

| Risk | Mitigation |
| --- | --- |
| Gemma-4 architecture unsupported by converters | fallback chain: official GGUF → Ollama registry → cloud-only (the lanes are agnostic via the OpenAI-compatible client) |
| Quantization degrades the 26B below usefulness | Phase 0 bench gate + side-by-side per task vs. E4B; if it loses, the tier is removed |
| Laptop-runner availability | weekly/on-demand lanes, not latency-sensitive; a lost week is benign |
| Small-model hallucination | grammar-constrained JSON everywhere; mandatory citations; deterministic detectors upstream of every LLM call |

📝 **Fine-tuning remains REJECTED** (ADR-028 §4): the trigger is labeled
volume (>10k), not hardware. Phase 4 of this plan is the only path and
requires a new ADR.

## P2 INTEGRATION (template_MLOps, 1–2 months — unblocks v1.0.0)

| # | Deliverable | Concrete steps |
| --- | --- | --- |
| P2.1 | **L4 evidence**: real GKE+EKS rollout | `deploy-gke` and `deploy-aws` skills on the example service → capture `kubectl get pods/svc`, Grafana, cost → dated entries in `ops/VALIDATION_LOG.md` → screenshots to `docs/evidence/` |
| P2.2 | 4 pending runbooks | `docs/runbooks/`: `gke-rollout.md`, `eks-rollout.md`, `rollback-validado.md`, `coste-ventana-l4.md` — format of the 5 existing ones |
| P2.3 | 14-day shadow window (ADR-019 Phase 2) | activate the prediction logger on the example, daily capture cron, on day 14: drift report with `drift-check` |
| P2.4 | ADR-018 Phase 2: ingest + retrieval **+ pedagogical L-2b (ADR-037)** | **REUSE this stack**: `scripts/memory_ingest.py` + `scripts/memory_query.py` (file-based, BM25 same as F1.5) over `ops/audit.jsonl` + ADRs, `operational` namespace; **in parallel**, `scripts/pedagogy_query.py` (`pedagogical` namespace, disjoint corpus: the adopter's own private pedagogical corpus + ADRs-as-prose) — two scripts, two indexes, one shared E4B (agent-local ADR-008). Both with file:line citations validated against their own namespace (§L-2b) |
| P2.5 | `data-cleaning` skill + module | `agentic/skills/data-cleaning/SKILL.md` (AUTO mode) + `templates/common_utils/data_cleaning.py` (imputation, outliers, types — with tests) + sync adapters + strict validator |

## P3 INTEGRATION (strategic)

1. **README niche** (first paragraph): "Supervised tabular ML on K8s, 1–10
   models, GCP/AWS, with documented outputs to Vertex/SageMaker".
2. **Agentic evaluation harness in CI**: scenarios where the agent MUST
   escalate/refuse per AUTO/CONSULT/STOP, built on the existing red-team
   log. Same `evals/run.py` runner — the sets live in `agentic/evals/`.
   Gate in `validate-templates.yml`.
3. **LLM-serving variant of the template**: evaluate as a separate track ONLY
   after v1.0.0 (ADR required; the store assistant is the case study).

## COMPARATIVE EVIDENCE portfolio vs. template (TWO experiments)

> These are two distinct questions and each needs its own experiment. Mixing
> them destroys the credibility of both.

### E-A: Parity migration (validates the TEMPLATE as a container)

Port the portfolio pipeline AS-IS (same features, same algorithm, same
hyperparameters, same seed) onto the template's scaffold.

| Dimension | Portfolio (manual) | Template (measure) |
| --- | --- | --- |
| Time to deployable service | weeks (actual) | hours (`new-service.sh` + data) |
| Lines written by hand | all | only `train.py` + features |
| Serving incidents | 3 suffered | 0 (D-01..D-32 prevent them) |
| Automatic gates | after the fact | day zero |
| Metrics | AUC 0.87 | **≈ equal — parity = faithful migration** |

### E-B: Assisted re-development (validates the agentic PROCESS end-to-end)

Start ONLY from the raw dataframe and run the full assisted cycle: skill
`eda-analysis` → skill `data-cleaning` (P2.5) → feature engineering → model
selection + HPO (Optuna) → gates (leakage, fairness) → serving. Here the
process is NOT identical to the manual one, so the metrics CAN and often do
improve — through identifiable mechanisms: more systematic cleaning, leakage
caught by the gate, more disciplined hyperparameter search, broader model
selection.

**Stated objective**: at minimum, parity in a fraction of the time; as a
stretch goal, attributable improvement. **Honesty guardrails** (without these
the experiment is worthless):

1. **Same frozen test set** as the portfolio, untouched — no "test until you
   win" (that's test-set shopping, not improvement).
2. Every metric delta **attributed to its mechanism** in MLflow: baseline run
   vs. assisted run, with the concrete change labeled (e.g. "per-group
   imputation", "feature X removed by leakage-gate", "HPO 200 trials vs. 30
   manual").
3. Validation with temporal CV identical to the original.
4. If the improvement doesn't materialize, it gets published anyway: "parity
   in 1/10th the time" is already an engineering win.

The interview line: *"the template doesn't improve the model by magic; it
improves the PROCESS that produces the model — and a better process finds
improvements the manual approach left on the table, each one traced in
MLflow"*.

Output of both: `docs/evidence/COMPARATIVE_BANKCHURN.md` with both tables +
links to the MLflow runs.

---

## FAULT-INJECTION DRILL — known-answer monitoring (leverages the portfolio datasets)

> Maintainer's idea, adopted: since we're already testing the portfolio
> datasets, **we deliberately inject the failures documented in the ADRs** and
> verify that the CORRECT monitoring surface detects them. This turns "the
> system detects failures" (a claim) into "I injected THIS known failure and
> the expected alarm fired in T seconds" (ground-truth evidence).

⚠️ **Critical distinction (don't lose it)**: the incidents from the ADRs are
**distinct failure classes**, each with its own detection surface. Lumping
them all under "drift" is the mistake that would make monitoring look
useless.

| Failure (source) | Class | How it's injected | Surface that MUST detect it | Expected result |
| --- | --- | --- | --- | --- |
| 81% errors (D-01) | concurrency/serving | overlay with `uvicorn --workers 4` | load test: error-rate + p95 | error-rate ↑, not drift |
| Zero SHAP values (D-04) | compatibility bug | TreeExplainer on the Stacking model | **contract test** | red test in CI, not runtime |
| HPA doesn't scale down (D-03) | infra config | memory-based HPA in overlay | replica count over time | flat replicas after traffic drop |
| Data leakage (ChicagoTaxi) | training integrity | reintroduce the leaked feature | **leakage gate** in `train.py` | promotion blocked |
| **Data drift** | distribution | perturb 1-2 features | PSI in `run_drift_drill.py` | PSI > threshold, alert |
| **Concept drift** | X→y relationship | invert the relationship in a slice | sliced performance | slice metric drops |

**Deliverable**: `templates/scripts/drills/fault_injection_matrix.py` — one
case per row, each with: an injection function, the expected surface, and an
assert that "this alarm and no other should have fired." Every run emits an
entry to `VALIDATION_LOG.md` (failure, expected surface, observed alarm,
detection time).

**Why it matters for the portfolio/CV**: it doesn't just test monitoring — it
demonstrates you know **which surface catches each failure class**, the
judgment that separates a junior from someone with production experience.
And it's recordable (audiovisual piece E18) BEFORE any cloud L4: it only
needs the local service + local monitoring. The best evidence-to-cost ratio
in the guide.

**Honest gate**: each row must be detected on ITS OWN surface (not another
one). If you inject data-drift and the contract test fires but NOT the PSI,
the bug is in your drift detector, not in the drill — and that too is a
finding that gets published.

---

## Global schedule and acceptance criteria

| Week | Milestone |
| --- | --- |
| 1 | F0 complete (bench + RESULTS.md) · P2.5 data-cleaning skill |
| 2–3 | F1 complete (router+loop+retrieval+dev webhook, read-only) · P2.4 ingest |
| 4–5 | F2 (policy, verifier, 10 sets) · P2.1–P2.2 L4 rollout + runbooks |
| 6–7 | F3 (logging, shadow) · P2.3 close 14d window · comparative experiment · **fault-injection drill (E18)** |
| 8 | P3.1–P3.2 · template release candidate v1.0.0 |

**Global acceptance** (final checklist): router picks the right tier in the
vast majority of cases · resolves product ambiguity with ONE question at most
· zero stock hallucination (evals 09/10 green) · stable on the laptop (one
large model active at a time) · 31B used selectively · everything testable
and observable · no response exposes chain-of-thought.
