---
name: doc-drift-fix
description: Use when CI reports doc drift or code changes API routers, tasks, models, services, mobile/web routes, Safety rules, specialists, or HealthTwin partitions.
---

# Doc-Drift Fix

架构计数和 roster 的唯一文档真源是代码生成的 `docs/_generated/system-map.json`。叙事文档只写稳定职责、流程和代码锚点；不要手改动态数字。

## 标准修复

```bash
./scripts/system-map-check.sh
```

中央 wrapper 使用项目固定的 Python 3.12 环境，串行验证并在需要时明确提示如何重新生成 System Map、Mobile nav 与 doc-drift 产物。它必须 exit 0；不要绕过它拼装较弱的局部命令。

## 按报错处理

| 报错 | 修复 |
|---|---|
| `system-map.json 与代码不符` | 确认代码是目标状态，运行生成器并提交更新后的 JSON |
| `architecture narrative: mutable count` | 从活跃叙事删除手写动态计数，改为链接 `_generated/system-map.json`；不要把数字改成“当前正确值” |
| `unknown rule file(s) not in EXPECTED` | 在 `EXPECTED["safety_rules"]` 登记新规则文件；纯数据文件登记为 `0` |
| Safety/Specialist/Twin expected 与代码不符 | 先确认变更是故意的，再同步 `EXPECTED` 安全契约并重新生成 system-map |
| 生成器 import 失败 | 修复依赖或环境问题；禁止空捕获、静默 fallback 或伪造快照 |

## 新增代码派生结构

当一类结构会随代码变化时，在 `scripts/dump_system_map.py::build_map` 增加字段，并复用 `scripts/check_doc_drift.py` 的扫描器。不要把新计数放进 ARCHITECTURE、agent 入口或 system-map 叙事。

## 提交前

- `git diff --check`
- `./scripts/system-map-check.sh`
- 只提交本任务文件，不使用 `git add -A`
