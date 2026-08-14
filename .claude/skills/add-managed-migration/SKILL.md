---
name: add-managed-migration
description: "给 backend 加 managed DB 迁移并做本地验证。自动 release 不得应用生产迁移；server-local manual-admin utility 单独获权。"
---

# Add Managed Migration

本仓库**无 Alembic**。结构迁移 = `backend/migrations/managed/` 下**成对的两个 SQL 文件**
(PostgreSQL 生产 + SQLite 测试/CI)。历史自动协议由 `deploy.sh -b` 按 checksum 应用；当前
该入口冻结，不能执行生产迁移。

## 何时需要

改了 `backend/app/models/*.py` 的表结构(加列 / 加表 / 加索引)→ 必须配一对迁移,否则生产/CI 的库没这列 → 运行时炸。**纯逻辑改动不需要。**

## 步骤

1. **文件名**:`YYYYMMDD_HHMMSS_<desc>.{postgresql,sqlite}.sql`,时间戳排在现有最新之后(`ls migrations/managed/ | sort | tail`)。
2. **写两个文件**(语法差异):
   ```sql
   -- *.postgresql.sql — 用 IF NOT EXISTS
   ALTER TABLE outcome_metrics ADD COLUMN IF NOT EXISTS confidence VARCHAR(12);
   ```
   ```sql
   -- *.sqlite.sql — SQLite 不支持 IF NOT EXISTS,裸 ADD COLUMN(靠 runner checksum 去重防重跑)
   ALTER TABLE outcome_metrics ADD COLUMN confidence VARCHAR(12);
   ```
3. **改模型**:`backend/app/models/*.py` 加对应 `Column(...)`(nullable / 有默认 → 向后兼容,旧行 NULL)。新类型记得 import(如 `Boolean`)。
4. **改了 model 文件数** → 走 `doc-drift-fix`(ARCHITECTURE.md models 计数);改了 service 同理。
5. **测试**:用 conftest 的 `db` fixture(in-memory sqlite 自动建表,但 managed 迁移**不**在测试里跑——测试靠 `Base.metadata.create_all`,所以**新列必须在模型上**才会出现在测试 sqlite 里。迁移文件是给生产/CI-真库的)。
6. **发布 Gate**：交 `backend-deploy` 记录 BLOCK；自动 `deploy.sh -b` 不得应用迁移。只
   保留迁移文件、模型与本地测试证据。若另有 production migration 需求，必须进入生产
   主机的独立、显式、获权 manual-admin 事件并留审计，且不能由自动 release 入口调用。

## 关键点

- 列要 **nullable 或有默认**,旧行才不炸(R16 的 `significant`/`confidence` 就是 nullable)。
- runner 按 checksum 记录已应用迁移,**改已应用的迁移文件内容不会重跑**——要补改另写一个新迁移。
- 生产是 PostgreSQL,测试/CI 是 in-memory SQLite,本地 dev 也是 PostgreSQL。别给 `DATABASE_URL` 指向 sqlite 文件(代码有 JSONB/TIMESTAMPTZ 假设)。
- 迁移涉及敏感表(用药/基因/化验/CGM)→ 上线走 `safety-gate`。

## 应用机制(排错用)

自动 release 的未来协议会由 managed runner 扫 `migrations/managed/*.<dialect>.sql` 并以
`schema_migrations` checksum 去重；当前自动调用只作设计/测试参考。独立 manual-admin
迁移事件不属于该自动发布机制，必须单独授权、解析目标并记录恢复/审计证据。
