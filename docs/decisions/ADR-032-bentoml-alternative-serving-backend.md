# ADR-032 — BentoML as an Optional Alternative Serving Backend

- **Status**: Proposed
- **Date**: 2026-06-30
- **Deciders**: Template maintainer (DuqueOM)
- **Related**: R7 Staff/Lead audit (`docs/audit/AUDIT_R7_STAFF_LEAD.md` §4), ADR-001
  (template scope boundaries), ADR-029 (agentic adoption contract), rule
  04a-python-serving (serving invariants D-01/D-03/D-04/D-24)

## Context

The template's serving path is hand-rolled: FastAPI + `asyncio.run_in_executor` +
`ThreadPoolExecutor`, with the model loaded by an init container into an
`emptyDir`. This is correct, dependency-light, and fully governed by the serving
invariants (1 worker per pod, CPU-only HPA, no model baked into the image, no
`model.predict()` on the event loop).

The R7 audit observed that **[BentoML](https://github.com/bentoml/BentoML)** is
the one frontier tool with real ROI for *this* template's identity: it offers
best-in-class model-packaging and serving DX — `bentoml.Service`, adaptive
batching, a runner abstraction — that our hand-rolled path does not. The audit's
recommendation was explicit: *evaluate BentoML as an ADR-tracked alternative
serving backend; do not mandate it.*

The risk is identity dilution. The template's value is governance + production
discipline, not serving-framework breadth. Adopting BentoML as the *default*
would add a heavy dependency and could erode the "minimal, inspectable serving
path" property. Adopting it as an *option behind the same invariants* captures
the DX upside without that cost.

## Options Considered

| Option | Pros | Cons |
| -------- | ------ | ------ |
| **A. Keep FastAPI-only (status quo)** | Minimal deps; fully inspectable; already governed | No adaptive batching; more serving boilerplate per service |
| **B. Replace serving with BentoML (default)** | Best serving DX; less boilerplate | Heavy dependency; identity dilution; re-validates every serving invariant against a framework we don't control |
| **C. BentoML as an *optional* backend behind the same K8s/HPA invariants (proposed)** | Captures DX for teams that want it; default stays minimal; invariants unchanged | Two serving paths to document and test; needs a contract proving BentoML honors D-01/D-23/D-25 |

## Decision (proposed)

Adopt **Option C**, staged and gated — do **not** implement yet:

1. **Phase 0 (this ADR).** Record the seam and the invariants any BentoML
   backend MUST satisfy: 1 uvicorn/Bento worker per pod (D-01), CPU-only HPA
   (D-02), model loaded via init container + `emptyDir` (D-11), distinct
   liveness/readiness paths (D-23), graceful shutdown ≥ uvicorn timeout (D-25),
   SHAP in original feature space (D-04). No code.
2. **Phase 1 (if pursued).** A `serving_backend` Copier choice (`fastapi` |
   `bentoml`) that renders one or the other, with a shared contract test
   asserting both backends honor the same `/health`, `/ready`, `/predict`,
   `/metrics` API (rule 14) and the serving invariants above.
3. **Phase 2.** Promote only if a measured benchmark shows BentoML's adaptive
   batching beats the FastAPI path on p95 latency / throughput for a
   representative model, with no invariant regressions.

This ADR is **Proposed**, not Accepted: it commits to the evaluation seam and
the invariant contract, not to shipping BentoML.

## Consequences

**Positive** — gives teams that value serving DX a governed on-ramp without
changing the default; documents the exact invariant contract up front so a
future implementation can't quietly violate D-01/D-23/D-25.

**Negative** — if pursued, doubles the serving surface to test and document;
adds an optional heavy dependency.

**Neutral** — until Phase 1 is approved, this is documentation only; the
FastAPI path remains the sole shipped backend.

## Revisit When

- A real adopter needs adaptive batching or the BentoML runner model, **or**
- A benchmark shows the FastAPI path is the latency/throughput bottleneck for a
  representative service. Absent either signal, the status quo (Option A) holds.
