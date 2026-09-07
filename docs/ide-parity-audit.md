# IDE Parity Audit — Devin / Cursor / Claude Code / Codex

Date: 2026-05-03

`AGENTS.md` defines the behavior protocol and `agentic/` remains the
canonical body store for rules, skills, and workflows. Cursor, Claude
Code, and Codex are now adapter surfaces generated from
`templates/config/agentic_manifest.yaml`.

## Current Parity

| Asset | Canonical (`agentic/`) | Cursor | Claude | Codex |
| ------- | ------------------------ | -------- | -------- | ------- |
| Rules | 15 canonical files (mirrored to `.devin/`) | 15 `.mdc` pointers | 15 `.md` pointers | 15 `.md` pointers |
| Skills | 16 canonical `SKILL.md` files | 16 pointers + `INDEX.md` | 16 pointers + `INDEX.md` | 16 pointers |
| Workflows | 12 canonical files | 12 command pointers | 12 command pointers | 12 workflow pointers |
| Context | `.devin_context.md` | `.cursor_context.md` | `.claude_context.md` | `.codex_context.md` |
| MCP example | User-home config | User-home config | User-home config | `.codex/mcp.example.json` |

The repository may still use the human shorthand "14 rules"; the
canonical on-disk count is 15 because rule 04 is split into serving and
training files.

## Enforcement

The parity contract is enforced by:

```bash
python3 scripts/sync_agentic_adapters.py --check
python3 scripts/validate_agentic_manifest.py --strict
python3 scripts/mcp_doctor.py --mode check
```

`sync_agentic_adapters.py` writes pointer files only. It must not copy
canonical `agentic/` bodies into another surface.

## Extension Pattern

To add a new IDE or agent platform:

1. Add the surface to `templates/config/surface_capabilities.yaml`.
2. Add the surface roots to `templates/config/agentic_manifest.yaml`.
3. Add the surface to the `surfaces:` list for the rules, skills, and
   workflows it can actually execute.
4. Add an `.*_context.md` pointer to `AGENT_CONTEXT.md`.
5. Run `python3 scripts/sync_agentic_adapters.py`.
6. Run the strict manifest validator and MCP doctor.

If the new platform requires native syntax beyond a pointer file,
extend the sync script with a surface-specific backend. Do not fork the
canonical rule, skill, or workflow bodies.

## See Also

- `AGENTS.md`
- `docs/decisions/ADR-023-agentic-portability-and-context.md`
- `templates/config/agentic_manifest.yaml`
- `templates/config/surface_capabilities.yaml`
- `templates/config/mcp_registry.yaml`
