---
name: doc-drift-fix
description: "doc-drift 红了 / 加了 model·service·API路由·safety规则·twin分区·celery任务·mobile路由 后同步文档计数。当 CI 报 doc-drift、或新增上述任一类文件时使用,避免 CI 卡住。"
---

# Doc-Drift Fix

`scripts/check_doc_drift.py` 校验 CLAUDE.md + docs/ARCHITECTURE.md 里硬编码的架构数字与代码一致。加了东西就得同步,否则 CI 红。

## 跑它

```bash
cd backend && source venv/bin/activate
python ../scripts/check_doc_drift.py     # exit 0 = 干净;非 0 = 列出每条漂移
```

## 它校验什么 + 漂移了改哪

| 改了什么 | 改这里 |
|---|---|
| `safety_guardian/rules/*.py` 加/删 `@register` | `scripts/check_doc_drift.py` 的 `EXPECTED["safety_rules"]`(per-file 计数)+ CLAUDE.md 的「Safety Guardian 规则分类」表(total N + 该文件行)+ ARCHITECTURE.md「N 条规则」 |
| **新增 rules/ 下的 .py(哪怕无 @register 的纯数据文件)** | **必须在 `EXPECTED["safety_rules"]` 登记**(数据文件登记为 `0`),否则报 `unknown rule file(s) not in EXPECTED`(踩过:`pgx_cpic_table`) |
| 加/删 specialist | `EXPECTED["specialists_count"]` + ARCHITECTURE.md「13 个 Specialist」 |
| HealthTwin 加/删**顶层分区**(非嵌套模型) | `EXPECTED["twin_partitions"]` + ARCHITECTURE.md「N 分区」。注:给现有分区加字段、加嵌套 BaseModel **不算**分区(分区 = HealthTwin 顶层字段数 − {meta, gene_config}) |
| `backend/app/services/**/*.py` 加文件 | ARCHITECTURE.md 两处 `N services`(一页概览框 + 技术栈表) |
| `app/api/main.py` 加 `include_router` | ARCHITECTURE.md `N API 路由` |
| `app/models/*.py` 加文件 | ARCHITECTURE.md `N models` |
| `app/tasks/**` 加 `@celery_app.task` | ARCHITECTURE.md `N Celery 任务` |
| `mobile/app/**/*.tsx`(非 `_layout.tsx`)加路由 | ARCHITECTURE.md mobile 路由数 |
| `frontend/src/app/**/page.tsx` 加页 | ARCHITECTURE.md web 页数 |

## 工作法

1. 让代码处于目标状态(加完文件)。
2. 跑脚本 → 它**逐条**列出「doc 写着 X,代码实际 Y」。
3. 按上表逐条改文档数字(`assert_doc_number` 会检查**所有**命中,防"一处对一处错"的部分漂移)。
4. 重跑直到 exit 0。

## 注意

- ARCHITECTURE.md 常被并发改动(别的 agent 也在加),改前 `git pull --rebase`,改后以脚本输出的实际数字为准(别钉旧数)。
- service 计数是 **recursive**(含 `cgm/`、`llm/`、`notification/` 等子目录)。
- 不要为了过 CI 去改 `EXPECTED` 迁就错代码——`EXPECTED` 只在代码数字**故意**变时才动。
