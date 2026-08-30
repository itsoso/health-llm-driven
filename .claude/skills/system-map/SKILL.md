---
name: system-map
description: "Use when onboarding to this repository, tracing cross-component or cross-end flows, verifying architecture facts or generated counts, changing code-derived system structure, or fixing System Map/doc drift. Do not load for non-repository meta questions or a known-path local edit unless the Router selects it."
---

# System Map

`docs/_generated/system-map.json` is the canonical code-derived graph. `docs/system-map/INDEX.md`, `docs/_generated/system-map-agent-context.md`, and query output are navigation views, not additional truth sources.

The bootstrap has a 4 KiB hard budget and focused query output has a 12 KiB hard budget. `complete`, `partial`, and `declaration` are coverage boundaries, not equal confidence levels; only 生成字段 may be described as drift-proof. JSON Schema validates `schema_version`, `entities`, and `relations`; the semantic contract validates IDs, ordering, and sources. Narrative 叙事 remains freshness-dated.

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

This central gate checks canonical equality, schema/semantics, `mobile/scripts/dump_nav_graph.py --check`, and doc drift. `/admin/system-map` is a read-only view of the same artifact. S8 must regenerate affected artifacts before the gate. Wide queries must be narrowed or intentionally given more depth/output budget; silent truncation is forbidden.

证据优先级：代码与测试 > 代码派生 System Map > 受审声明 > 带新鲜度的叙事。地图不能替代源码和测试验证。
