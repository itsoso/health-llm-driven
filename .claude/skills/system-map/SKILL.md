---
name: system-map
description: "Use when onboarding to this repository, tracing cross-component or cross-end flows, verifying architecture facts or generated counts, changing code-derived system structure, or fixing System Map/doc drift. Do not load for non-repository meta questions or a known-path local edit unless the Router selects it."
---

# System Map

`docs/_generated/system-map.json` is the canonical code-derived graph. `docs/system-map/INDEX.md`, `docs/_generated/system-map-agent-context.md`, and query output are navigation views, not additional truth sources.

## Read strategy

1. Run the governance Router first. Use this skill only when selected or when the task clearly matches the trigger above.
2. For a known path/entity/flow, query directly; default to zero-hop:

   ```bash
   python3.12 scripts/system_map_context.py --path backend/app/api/ --depth 0
   python3.12 scripts/system_map_context.py --entity component.mobile --depth 0
   python3.12 scripts/system_map_context.py --flow agent-chat
   python3.12 scripts/system_map_context.py --counts
   ```

3. For onboarding, whole-system architecture, or cross-domain design, read `docs/system-map/INDEX.md` and the bounded generated bootstrap before the focused query.
4. Open every relevant source path and nearby test before drawing conclusions. `partial` or `declaration` coverage always requires source verification.

## Maintenance

Never hand-write live counts or rosters into narrative docs. When generated structure changes, update the generator/declarations, regenerate artifacts, and run:

```bash
./scripts/system-map-check.sh
```

Wide queries must be narrowed or intentionally given more depth/output budget; silent truncation is forbidden. Evidence priority is code and tests, generated graph, reviewed declarations, then dated narrative.
