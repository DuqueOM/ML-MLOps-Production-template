# Architecture Decision Records

This directory holds **two different things**, and telling them apart matters.

## 1. Your service's ADRs — you write these

Record your own decisions here, starting at `ADR-001`. Use
[`adr-template.md`](adr-template.md) as the skeleton, or run the `/new-adr`
workflow.

These are yours. Nothing in the template will overwrite them, and
`copier update` will not touch files it did not generate.

## 2. The template's ADRs — inherited, not yours

A handful of the template's own decision records ship with the generated
service because runtime code and agentic rules reference them directly:

| File | What it governs |
| --- | --- |
| `ADR-010-dynamic-behavior-protocol.md` | AUTO / CONSULT / STOP modes + dynamic risk escalation |
| `ADR-014-gap-remediation-plan.md` | Remediation programme the invariants came from |
| `ADR-018-operational-memory-plane.md` | Operational Memory Plane contracts |
| `ADR-019-agentic-ci-self-healing.md` | CI self-healing classifier + policy |
| `ADR-023-agentic-portability-and-context.md` | Vendor-neutral agentic surface |
| `ADR-043-audit-quality-guardian.md` | Recurring enterprise-audit bar |

**These use the template's numbering, not yours.** That is the collision
this file exists to defuse.

## The numbering collision, stated plainly

Template-provided files — `AGENTS.md`, `CLAUDE.md`, the `agentic/` rule
store, contract tests, config schemas — cite decisions as bare
`ADR-NNN`. Those identifiers belong to **the template's** numbering
sequence.

Two consequences:

1. **A bare `ADR-NNN` in a template-provided file is a template ADR**, even
   when you also have an `ADR-NNN` of your own. `ADR-017` in a template
   file means the template's ADR-017, not yours.
2. **Most of them are not in this directory.** The template has 40+ ADRs
   and ships 6; the rest are referenced but not vendored, because copying
   the template's entire governance history into every generated service
   would be worse than a pointer. Resolve any of them at:

   <https://github.com/DuqueOM/ml-service-template/tree/main/docs/decisions>

If your repo runs a link or reference checker, this is why it may flag
`ADR-027` or similar as unresolved: it is a **template** ADR, resolvable at
the URL above, not a missing file in your repo.

### Recommended convention for your own prose

When *your* documents cite a template decision, write it as
**`template-ADR-NNN`**. That keeps your numbering unambiguous without
touching any template-provided file.

The template-provided files themselves are deliberately **not** rewritten
to that form: several of them (`agentic/`, the shipped ADRs, config
schemas) are held byte-identical to the upstream template by a drift gate,
so rewriting identifiers here would either break that gate or fork you from
upstream. A pointer costs nothing; a fork costs every future
`copier update`.

## Why the template's ADRs ship at all

Because the runtime reads them. The AUTO/CONSULT/STOP protocol in
`ADR-010` and the portability contract in `ADR-023` are not background
reading — agentic tooling in this service resolves behaviour against them.
Shipping the pointer without the content would make those rules
unverifiable offline.
