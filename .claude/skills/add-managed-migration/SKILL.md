---
name: add-managed-migration
description: "给 backend 加一个 managed DB 迁移(改表结构 / 加列 / 建表)。PostgreSQL 是生产与语义真源；本仓库无 Alembic，迁移保留 PostgreSQL 主文件与 SQLite 兼容性镜像，deploy.sh -b 自动应用匹配生产方言的文件。"
---

# Add Managed Migration

本仓库**无 Alembic**。结构迁移 = `backend/migrations/managed/` 下**成对的两个 SQL 文件**(PostgreSQL 权威迁移 + SQLite 兼容性镜像),`deploy.sh -b` 自动按数据库方言应用(checksum 去重,已应用的跳过)。

测试矩阵不是二选一：SQLite 兼容性适合快速单元/迁移回放；生产语义、并发、约束、JSONB、时区和 PostgreSQL 特有行为必须有 PostgreSQL 语义集成证据。

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
5. **测试**:
   - 快速单元可用 conftest 的 SQLite `db` fixture；它靠 `Base.metadata.create_all`，所以新列仍必须同步到模型。
   - SQLite 迁移镜像要做迁移兼容性回放。
   - 新数据库行为必须补 PostgreSQL 语义集成测试；不能用 SQLite 绿替代 PostgreSQL 约束、并发、JSONB、时区或方言语义。
6. **上线**:`backend-deploy`(`deploy.sh -b` 自动 apply;日志出现 `managed migrations applied: <你的文件名>`)。

## 关键点

- 列要 **nullable 或有默认**,旧行才不炸(R16 的 `significant`/`confidence` 就是 nullable)。
- runner 按 checksum 记录已应用迁移,**改已应用的迁移文件内容不会重跑**——要补改另写一个新迁移。
- 生产和开发权威数据库是 PostgreSQL；CI 同时保留 SQLite 快速 lane 与 PostgreSQL 语义集成 lane。SQLite 绿不能作为 PostgreSQL 特有行为的完成证据。
- 迁移涉及敏感表(用药/基因/化验/CGM)→ 上线走 `safety-gate`。

## 应用机制(排错用)

`deploy.sh -b` → `backend/scripts/apply_managed_migrations.py`:扫 `migrations/managed/*.<dialect>.sql`,按 `schema_migrations` 表的 checksum 跳过已应用,新的按文件名顺序执行。`-b` 日志里 `managed migrations applied/skipped` 两行能看到结果。
