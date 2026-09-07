# Architecture Review — Local-First Agentic Framework

> Requested by the maintainer (2026-06-12) with an explicit mandate for
> active critique: *"do not assume the current decisions are correct."*
> This review challenges the current plan (`ACTION_PLAN_LLM_AGENT.md` v2),
> validates what survives scrutiny, and proposes changes where something
> better exists. Verdicts in **bold** at the end of each section.

---

## 0. Executive summary (the 6 decisions that matter)

| # | Question | Verdict |
| --- | --- | --- |
| 1 | n8n as the framework's orchestrator? | **NO in the agentic core. YES, optionally, as an integration/edge layer** (webhooks, SaaS connectors) |
| 2 | Temporal/Camunda/Airflow? | **Not now.** Temporal is the right candidate IF this becomes a multi-tenant product; Camunda/Airflow don't fit agentic loops |
| 3 | Agent framework (LangGraph, CrewAI, AutoGen...)? | **Not for the core.** A custom loop in Python/FastAPI is the right call — with LangGraph as the only future re-evaluation if the state graph grows |
| 4 | Executive Controller as a component? | **Yes, but as a module, not a service**: it already exists implicitly (router+budget+policy+telemetry); naming it and giving it a single interface is the real improvement |
| 5 | The 4 Gemma models? | **3 confirmed, 2 conditional**: E4B and 26B-A4B are the core; 12B and 31B live under eval clauses (already codified). Missing: a small **embedding model** |
| 6 | Is the 7-station loop optimal? | **Yes, for this domain.** Tree-search/debate/multi-agent: rejected with arguments (below). Only addition: self-consistency K=3 ONLY in high-stakes cases |

---

## 1. Overall architecture — an honest critique

**What is right and survives scrutiny:**

- Local-first with cloud as an explicit release valve: correct for
  customer/pricing data and zero marginal cost.
- Pydantic contracts at every boundary: this is what makes the system
  testable.
- A deterministic policy gate separated from the model: the single most
  important design decision; no framework on the market gives you this
  for free.

**Real weaknesses identified (not cosmetic):**

1. **SPOF: the laptop.** A single host runs models, gateway, tools, and
   memory. Honest mitigation (not "buy a cluster"): per-port healthchecks +
   degradation to templates + a persistent queue (SQLite/WAL) so a
   restart doesn't drop WhatsApp messages. *Accepting* the SPOF is fine
   at this stage; losing messages is not.
2. **Missing an explicit queue.** The plan says "enqueue and return 200"
   but doesn't define THE component. Verdict: **SQLite as the persistent
   queue** (one table, one worker per conversation). Not Redis/RabbitMQ
   yet — another piece of infrastructure to maintain without the traffic
   to justify it.
3. **Missing the embedding model in the tier table** (see §6).
4. **Unnecessary component detected: none.** The design is already lean;
   the plan's risk isn't excess but executing the phases in order.

---

## 2. Model routing — too many or too few?

Critique of the 4-model lineup:

- **E4B (router)**: essential. Nothing cheaper classifies with grammar
  constraints.
- **26B-A4B (assistant)**: essential. The MoE is the only way to get
  26B-scale knowledge at interactive latency within 8GB VRAM.
- **12B**: the most questionable. My critique: its niche (mid-tier
  reasoning) overlaps with both neighbors. The buffer clause (retire if
  2 eval cycles don't justify it) **is already the right answer** — but
  I propose tightening it further: *start WITHOUT the 12B in production*
  (router skips 0→2) and only introduce it if telemetry shows the 26B
  spending >25% of its time on tasks that eval set 07 classifies as
  "medium." Burden of proof inverted.
- **31B (judge)**: correct ONLY as a batch judge (already codified). Do
  not procure until eval 10 fails with the 26B as verifier.
- **MISSING: an embedding model** (~0.5GB, e.g. a small multilingual
  embedder) — not for a vector store yet, but for the **semantic router**
  (below) and the lightweight reranker in hybrid retrieval (§6).

**Routing strategies evaluated:**

| Strategy | Verdict |
| --- | --- |
| Confidence routing | ✅ already adopted (v2) — calibrate with eval 01 |
| Budget/latency-aware | ✅ already adopted (`RequestBudget`) |
| **Semantic routing** | ✅ **ADOPT**: embeddings of known intents + cosine similarity BEFORE the E4B. Resolves 60-70% of repetitive traffic in <5ms without touching an LLM. The E4B becomes the semantic router's fallback, not the first line |
| Uncertainty routing (logit entropy) | ⚠️ defer: llama.cpp exposes logprobs, but calibrating entropy is a project of its own; declared confidence + evals is enough for now |
| Dynamic/quality-aware (bandits) | ❌ reject for now: optimizing online without volume is noise. Revisit with >10k logged conversations |

**Verdict §2: final routing pipeline =
`semantic cache → E4B with grammar → objective escalation`. The 12B
enters only with inverted burden of proof. Add a small embedder to the
inventory.**

---

## 3. Executive Controller

Should a higher-level component exist for routing/budgets/policy/telemetry/
escalation/retries/circuit breakers?

**Yes — but the right question is WHAT FORM it takes.** Critique of the
"separate service" version: a controller-service duplicates the network,
adds a latency hop, and a second SPOF to govern... a single host. That's
enterprise theater.

**Correct form: a `controller.py` module with a single interface** that
already exists, almost fully, scattered across the plan (router + budget +
policy + telemetry). Design:

```python
class ExecutiveController:
    """Single entry/exit gate for every request. Everything passes through here."""
    def admit(self, msg) -> tuple[Route, RequestBudget]      # semantic cache → route → budget
    def execute(self, route, budget) -> Draft                # delegates to the loop; applies retries/CB
    def release(self, draft) -> Final                        # policy gate → telemetry → response
```

Responsibilities that DO belong here: per-tier circuit breaker (3
failures on port 8093 → degrade to 8092 + templates, half-open at 60s),
retries (ONLY for idempotent tools, never for the whole loop), budget,
telemetry. Responsibilities that do NOT: business logic, prompts, domain
knowledge.

**Risk to watch**: the controller bloating into a god-object. The
defense: its three methods don't grow; the modules it orchestrates grow.

**Verdict §3: adopt as a module with the 3-method interface. This is
the #1 structural improvement in this review — it turns scattered
invariants into a single auditable point.**

---

## 4. Agent loop — is the 7-station design optimal?

Alternatives evaluated honestly:

| Pattern | Verdict | Why |
| --- | --- | --- |
| Current loop (plan→tools→observe→reflect→critic→policy→final) | ✅ correct baseline | maps 1:1 to the domain: live data + hard policies |
| **Self-consistency (K samples, vote)** | ✅ adopt ONLY in `risk=high` with K=3 | 3× cost justified only where an error costs money; elsewhere it's wasted latency |
| Tree search (ToT/MCTS) | ❌ | shines on puzzles with evaluable state; "do you have coke in stock?" has no tree to search. Complexity without signal |
| Multi-model debate | ❌ | doubles cost to win on open-judgment tasks; your verifier + policy gate already cover the real use case |
| Multi-agent (crews) | ❌ | N agents = N² failure surfaces and prompts to maintain. Anthropic itself: *the simplest loop that works*. Your real "multi-agent" already exists: the TIERS with a contract |
| Actor-critic | ✅ you already have it | generator (26B) + critic (26B/31B) IS actor-critic; doesn't need the label |
| Graph-based (LangGraph) | ⚠️ revisit if... | the day you have >3 flows with deep branching and need per-node state checkpointing. Today the graph is a single line with one cycle — a `while` loop with a budget expresses this better than a DAG framework |

**Verdict §4: loop confirmed + self-consistency K=3 in high-stakes cases
as the only addition. Everything else is complexity looking for a
problem.**

---

## 5. Orchestration — the comparison you asked for (n8n included)

First, the distinction that organizes the whole analysis. There are
THREE distinct problems that people all call "orchestration":

- **(A) Agentic loop** (seconds, in-memory state, the LLM decides the
  path)
- **(B) Durable workflows** (hours/days, persistent state, exact
  retries: orders, payments, sagas)
- **(C) Integration/ETL/connectors** (webhooks, SaaS, transformations)

| Tool | Type | Maturity | Enterprise-ready | Real strength | Why NOT for (A) |
| --- | --- | --- | --- | --- | --- |
| **n8n** | C | high | medium (fair-code license, not pure OSS; self-hosting is fine) | 400+ connectors, brutal integration speed | a loop with reflect/critic/policy expressed as visual nodes is unreadable, undiffable, and untestable; loop state is not a workflow, it's a conversation |
| **Temporal** | B | very high | **the reference** (Uber/Netflix/Stripe-class) | durable execution: the workflow survives crashes via deterministic replay | the determinism it requires clashes with non-deterministic LLMs (workable via activities, but you pay for a cluster + a learning curve for a laptop) |
| **Camunda** | B | very high | high (BPMN, banking/insurance) | BPMN-auditable business processes | BPMN models human-approval processes, not inference loops; absurd Java/Zeebe weight here |
| **Airflow** | C(batch) | very high | high in DATA eng | scheduled DAGs, backfills | it's a batch scheduler: seconds-to-minutes latency per task, a total anti-pattern for chat |
| **Argo Workflows** | B/C on K8s | high | high (CNCF) | native K8s workflows, already touched in the template | same problem: pods per step, not conversational loops |
| **LangGraph** | A | medium-high | medium (LangChain Inc., paid LangSmith) | state graphs with checkpointing for agents | the BEST external candidate for (A)... but it couples you to its runtime/abstractions, and your current loop fits in ~200 lines you understand 100% |
| OpenAI Agents SDK / Google ADK | A | medium/new | medium | native integration with THEIR cloud | gravitate toward their provider; your principle is local-first |
| CrewAI / AutoGen | A | medium | low-medium | fast multi-agent prototyping | rejected along with multi-agent (§4); thick abstractions, opaque debugging |
| Semantic Kernel | A | medium | medium-high (.NET/MS ecosystem) | plugins/planners in C#/Python | outside your stack; no advantage over your loop |
| PydanticAI | A | new | medium (Pydantic team, serious) | typed agents with the SAME contract philosophy as yours | the most ideologically aligned; still young — steal ideas, yes; depend on it, no |
| Haystack | RAG | high | medium-high | retrieval pipelines | this is for (§6), not the loop; and your file-based retrieval doesn't need it yet |

**Is n8n worth it ANYWHERE? Yes — in its own lane.** n8n is excellent as
a **perimeter integration layer**: receiving the WhatsApp webhook,
wiring up a CRM/Sheets/Telegram in minutes, notifying a human when the
agent escalates. That's (C), its territory. Concrete proposal: an
**optional `integrations/n8n/` track** in the template with an exported
flow (webhook → POST to the agent gateway → response), documented as an
adapter — the brain NEVER lives in n8n. For your learning/CV goal:
knowing n8n is a plus for automation roles; presenting it as an agent
orchestrator counts against you with a senior interviewer.

**And the underlying question — a custom Python/FastAPI engine vs.
adopting one?** **Custom engine, confirmed.** Non-accommodating
arguments:

1. Your differentiating core IS control (policy, budgets, contracts,
   audit). Delegating it to a framework gives away the template's thesis.
2. The complete loop is ~200-400 lines with ZERO magic. LangGraph saves
   you ~100 of them and costs you a dependency with high churn.
3. You'll learn more (stated goal) by building the engine and READING
   how LangGraph/PydanticAI solve checkpointing than by importing them.
4. Honest review clause: if you reach (a) >3 flows with deep graphs, or
   (b) a real need for multi-day durable execution → re-evaluate
   LangGraph (a) or Temporal (b) with an ADR. Written triggers, not
   dogma.

**Verdict §5: custom engine. n8n = optional edge adapter. Temporal =
future ADR with an explicit trigger. The rest: rejected with cause.**

---

## 6. Retrieval and memory — target architecture

The current ladder (file-based → BM25 → vector) is correct; what was
missing is a picture of the FINAL state so it isn't improvised later:

```text
query → [0 semantic cache (embeddings, exact hits)]
      → [1 alias/taxonomy (deterministic, products)]
      → [2 hybrid: BM25 + dense embeddings → RRF (reciprocal rank fusion)]
      → [3 lightweight reranker (top-20 → top-3 only, small cross-encoder)]
      → compact context with mandatory citations
```

- Taxonomy/ontology: the hierarchical `categorias.json` file IS ALREADY
  your ontology. Do not adopt a triple store; a versioned JSON file in a
  PR is more auditable.
- Customer memory: conversation summaries (generated by E4B, 1 paragraph,
  PII-redacted) + stable preferences. NEVER stock/prices (a sacred line).
- Vector DB: once the gate recall@5<80% fires — **sqlite-vec or LanceDB**
  (embedded, zero new services), NOT a managed Pinecone/Weaviate.
- The reranker and the embeddings reuse the embedder from §2.

**Verdict §6: adopt the target design; implement it gate by gate as
already agreed. Hybrid BM25+dense with RRF is the industry standard
(Elastic/Anthropic contextual retrieval) and your natural path.**

---

## 7. Policy Engine — enterprise-grade design

What exists today (deterministic checks + verifier) is the right
foundation. Reaching enterprise level requires three more pieces, all
cheap:

1. **Policies as data, not code**: move thresholds and rules to
   versioned `policies/*.yaml` (which tools each intent may call, maximum
   amounts, prohibited commitments, tone per channel). The runtime loads
   them; a PR changes them; the diff IS the compliance audit trail.
2. **Decisions with an ID**: every gate verdict emits
   `{policy_version, rules_fired, decision_id}` into telemetry — traceable
   from the customer's response back to the exact rule that allowed it.
3. **Two-person rule for new mutations**: a new write tool ships with
   `dry_run` forced until (a) its eval passes and (b) a human signs off on
   the PR that arms it. This is AUTO/CONSULT/STOP applied to tools.

❌ Rejected: OPA/Cedar/external policy engines — yet another runtime to
evaluate what 30 lines of Python + YAML express better at this scale.
Re-evaluation trigger: multi-tenant with per-customer policies.

---

## 8. Evaluations — the continuous system

Plan v2 already has the 10 sets + per-tier gates + shadow traffic. What
this review adds:

- **Frozen golden set** (50 cases, NEVER grows or gets edited) separate
  from the live set: measures long-term system drift; the live set
  measures coverage.
- **Replay as a first-class citizen**: JSONL telemetry must be
  re-executable
  (`evals/replay.py --from logs/2026-06-12.jsonl --against new-prompt`) —
  every prompt change is tested against yesterday's real traffic before
  seeing today's traffic.
- **Router eval as a published confusion matrix** per cycle, not just
  accuracy: over-escalation costs latency; under-escalation costs
  quality.
- Online: the already-agreed 10% shadow + the rate of "let me confirm
  and get back to you" (a proxy for policy blocks) as a product metric.

---

## 9. Observability — completing the picture

On top of the existing v2 telemetry, two additions and one rejection:

- ✅ **Trace ID per conversation** propagated to tools and tiers (one
  field, not a platform). When correlation pain becomes real:
  OpenTelemetry exporting to... the SAME Prometheus/Grafana already in
  the template. Zero new tools.
- ✅ **Cost per request** as a derived metric (tokens×tier + GPU
  seconds): module 21's FinOps applied to agents.
- ❌ LangSmith/LangFuse/W&B-LLM: pretty dashboards, early lock-in. Your
  JSONL + Grafana covers 90%; revisit with a team >1.

---

## 10. Future evolution (fine-tuning and beyond)

I confirm the current gate (Phase 4: >10k labeled events + a stable
pattern that prompting doesn't solve) and lay out the ladder with
triggers:

```text
TODAY: prompts + retrieval + evals
 └─ trigger >10k examples + persistent style gap
     → QLoRA on E4B/12B (tone, format, brand protocol) — NEVER facts
 └─ trigger: abundant preference pairs from judge verdicts
     → DPO/preference optimization (the critic's rejections ARE the dataset)
 └─ Classic RLHF/RLAIF: ❌ not on the visible horizon — cost/infra without a business case
 └─ Continual learning: via retrieval (memory learns), not via weights
```

The synthetic generation already agreed (reviewed regional variants) is
the only "data flywheel" you need this year.

---

## Actionable changes this review introduces to the plan

| # | Change | Phase |
| --- | --- | --- |
| R1 | Semantic cache/router with a small embedder in front of the E4B | F1.5+ |
| R2 | `ExecutiveController` as a 3-method module + circuit breakers | F2 |
| R3 | Persistent SQLite queue (one worker per conversation) | F1.6 |
| R4 | 12B out of the initial rollout; enters with inverted burden of proof | F2.1 |
| R5 | Self-consistency K=3 only in `risk=high` | F2.3 |
| R6 | `policies/*.yaml` + decision_id in telemetry | F2.2 |
| R7 | Frozen golden set + `evals/replay.py` | F2.5 |
| R8 | Optional `integrations/n8n/` track as a documented edge adapter | P3 |
| R9 | Trace ID + cost/request in telemetry | F3 |
| R10 | Written ADR trigger for Temporal (durable, multi-tenant) and LangGraph (>3 deep graphs) | P3 |

---

## ADDENDUM v3 — Adversarial review of R1–R10 (2026-06-12)

> Maintainer's mandate: subject the R1–R10 proposals themselves to the
> same scrutiny as everything else, without optimizing for agreement,
> proposing fifth alternatives where they exist. Honest result: **3
> proposals are revised downward, 1 is deferred with a trigger, 6
> survive with refinements.** Per-item format: attack → verdict →
> complexity/impact → priority.

## A-R1. Three-layer model (A/B/C) — REVISED DOWNWARD

**Attack**: does layer B (durable workflows) exist TODAY in this
system? There is only ONE latent case (order → confirmation → follow-up,
over days). Creating an architectural "layer" for a single case is
taxonomy without substance — the same theater we criticized in
microservices.

**Fifth alternative (adopted)**: **two layers + one pattern**. A (loop)
and C (integration) are real layers with dedicated code. B is not a
layer: it's the *durable-state-as-data* pattern — a `sagas` table in the
SAME queue SQLite (state, step, deadline, retries) + a periodic sweep by
the worker. Zero new runtimes; Temporal remains the ADR trigger if sagas
grow past ~3 types or require distributed exactly-once semantics.
**Complexity**: low (1 table + 1 function). **Priority: NOW** (F1.6).

## A-R2. n8n positioning — HARDENED AGAINST

**Attack on my own `integrations/n8n/` track proposal**: for a SINGLE
channel (WhatsApp), an n8n flow is one more container to operate, one
more auth surface, an undiffable exported JSON, and a fair-code license
in a template that prides itself on a clean supply chain. The FastAPI
webhook is 40 testable lines.

**Revised verdict**: the core stays code-first (confirmed); the n8n
track **is deferred with a trigger**: it is created only once ≥2 real
SaaS integrations exist (CRM + something else). Until then, n8n lives
only as a positioning paragraph in the docs. Any alternative as a
primary runtime? Re-evaluated Temporal/Camunda/LangGraph against a
5-10 year criterion: none displaces the custom runtime — the decisive
argument is that the template's differentiator IS control
(policy/budgets/audit), and that is not delegated.
**Priority: DEFERRED** (trigger written into P3).

## A-R3. ExecutiveController — SURVIVES with a refined shape

**Attack**: real god-object risk; also, an object with 6 sub-modules
accumulates shared mutable state.

**Refinement adopted**: the 3-method facade stays, but the interior is a
**pipeline of pure middlewares** (`admit = compose(normalize, cache,
route, budget)`) — each middleware a testable, isolated `(ctx) -> ctx`
function. Hard cap: ~250 LOC for the whole module; if it grows, it gets
split. Circuit breaker: state IN MEMORY (re-learns within seconds after
a restart; persisting it would be complexity without benefit).
**Complexity**: medium-low. **Priority: NOW** (F2.0).

## A-R4. Semantic router pre-E4B — REJECTED AS PROPOSED (my error)

**Attack (fatal)**: with ZERO traffic there is no "repeated traffic" to
cache — this is textbook premature optimization. Worse: in a COMMERCIAL
bot, a semantic-cache false positive answers about the wrong product (a
business risk, not just a latency one). And it adds one more model to
operate on day 1.

**Revised verdict**: the deterministic chain (normalizer → alias →
taxonomy → BM25) DOES ship on day 1 — zero new models, it was already
in the plan. The **embedder + semantic cache is deferred with a
measurable trigger**: when telemetry shows ≥30% near-duplicate queries
that the alias layer failed to resolve (measurable OFFLINE against the
logs, without serving embeddings). And when it does ship: **only the
ROUTE is cached, never the response** — every response still passes
through live tools + the policy gate.
**Priority: DEFERRED with a trigger** (F3, weekly offline analysis).

## A-R5. Model responsibilities — CONFIRMED with two caveats

**Caveat 1 (in favor of the 12B I dismissed too quickly)**: with 36GB,
12B (6.5G) and 26B (14G) DO co-reside — the "one large model at a time"
argument doesn't apply between them. Even so, operational simplicity
wins: **launch without the 12B** confirmed; adding it later is cheap once
telemetry justifies it (the artifact stays on disk).
**Caveat 2 (judge)**: for maintenance lanes WITHOUT PII (docs-drift,
template evals), a cheap-tier cloud judge can outperform the local 31B
on both quality and latency — permitted. For CUSTOMER high-stakes cases,
the judge stays local because of the privacy line: the 31B holds.
**Priority: NOW** (launch rule) / cloud judge noted in lanes.

## A-R6. Loop / reflection — REFINED (conditional reflect)

**Attack**: unconditional `reflect` adds a model pass (1–3s) to
tool-light intents where it adds nothing — wasted latency budget in the
common case.

**Refinement adopted — adaptive depth**: `reflect` runs ONLY if (a) a
tool failed or contradicted the plan, or (b) `risk≥medium`. Smalltalk
and clean lookups go plan→tools→policy→final.
**Self-consistency K=3**: my own proposal doesn't survive the budget —
3 passes of the 26B blow through WhatsApp's 8s budget. Revised: K=3
ONLY in ASYNCHRONOUS high-stakes flows (order confirmations where
15-20s is acceptable) and in nightly evals; interactive high-stakes uses
a single pass + judge.
**Priority: NOW** (it's an `if`, not a system).

## A-R7. Budget engine — CONFIRMED static, adaptive REJECTED for now

**Attack on "adaptive"**: self-adjusting budgets are one more feedback
loop to debug, with no data to ground it. **Verdict**: STATIC budgets
per intent in `budgets.yaml` (versioned, diffable) + a **daily cloud
cap** (a simple counter). Adaptivity: revisit with ≥4 weeks of real P95
data. Add `max_reflections: 1` to RequestBudget (closes A-R6).
**Priority: NOW.**

## A-R8. Policy YAML — SURVIVES with one extra requirement

Re-evaluated alternatives (Rego/OPA, CUE, a Python DSL): YAML+Pydantic
wins on auditability for non-engineers and on zero new runtimes.
**Added requirement**: every change to `policies/*.yaml` MUST ship with
its own case in eval set 06 that fails without the change
(policy-change-requires-test). Policies-as-data without tests is just
magic configuration.
**Priority: NOW** (F2.2).

## A-R9. Telemetry — ELEVATED to mandatory; OTel deferred, and deferred well

**Verdict**: telemetry moves from "good practice" to a **template
contract**: a lane that doesn't emit the event schema does NOT pass the
validator (the agentic equivalent of the D-20 prediction logger). OTel:
deferred, BUT field names are aligned to OTel semconv from today
(`trace_id`, `span`...) so the future migration is a transport swap, not
a mass rename.
**Priority: NOW** (naming) / OTel with a trigger (team >1 or >1 host).

## A-R10. Continual-learning pipeline — CONFIRMED with hard governance

**Attack**: capturing user corrections straight into datasets = privacy
risk AND poisoning risk (a malicious user "teaches" the bot).
**Governance adopted (non-negotiable)**: (1) PII redaction at the moment
the log is WRITTEN, not afterward; (2) **quarantine**: nothing enters a
dataset without batched human review; (3) per-record provenance
(`source`, `reviewer`, `policy_version`); (4) retention: raw 30 days,
curated indefinitely; (5) judge verdicts generate pairs for DPO — that
is the legitimate flywheel.
**Priority: the SCHEMA now** (telemetry fields), the pipeline in F4.

## Resulting integrated architecture (v3)

```text
WhatsApp/channels ──► FastAPI webhook (code-first; n8n = deferred trigger)
        │
        ▼
  SQLite queue (worker/conversation) + sagas table (durable-state-as-data)
        │
        ▼
ExecutiveController (3-method facade; pure middlewares; in-memory CB)
  admit:  normalize → alias/taxonomy/BM25 → E4B(grammar+confidence)
          → budget(budgets.yaml + daily cloud cap)
  execute: adaptive loop [plan → tools → observe → (reflect?) → critic]
           tiers: E4B / 26B (12B and semantic cache: written triggers)
  release: policy gate (policies/*.yaml + decision_id + mandatory test)
           → MANDATORY telemetry (OTel-compatible naming, PII-redacted,
             provenance fields for the DPO flywheel) → finalize
        │
        ▼ (no SLA / no PII)
   local 31B judge · cloud judge ONLY for maintenance lanes · nightly evals
```

| Item | v3 status | When |
| --- | --- | --- |
| Two layers + durable-state-as-data (sagas table) | adopted | F1.6 |
| n8n track | deferred (≥2 SaaS integrations) | trigger P3 |
| Controller facade+middlewares, ≤250 LOC | adopted | F2.0 |
| Deterministic chain pre-router | adopted (already in place) | F1.5 |
| Embedder + semantic cache | **deferred** (≥30% near-dups in logs; caches the ROUTE) | trigger F3 |
| Launch without 12B / cloud judge only for non-PII | adopted | F0/F2 |
| Conditional reflect + K=3 only async/evals | adopted | F1.6/F2.3 |
| Static budgets.yaml + cloud cap + max_reflections | adopted | F1.6 |
| policies.yaml + decision_id + policy-change-requires-test | adopted | F2.2 |
| Mandatory telemetry, OTel-compatible naming | adopted | F1–F3 |
| Flywheel governance (quarantine/provenance/retention) | schema now, pipeline F4 | F3/F4 |
