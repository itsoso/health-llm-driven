---
name: add-managed-migration
description: "给 backend 加一个 managed DB 迁移(改表结构 / 加列 / 建表)。当要改 SQLAlchemy 模型对应的表结构时使用。本仓库无 Alembic,迁移是 pg+sqlite 双文件,deploy.sh -b 自动应用。"
---

# Add Managed Migration

本仓库**无 Alembic**。结构迁移 = `backend/migrations/managed/` 下**成对的两个 SQL 文件**(PostgreSQL 生产 + SQLite 测试/CI),`deploy.sh -b` 自动应用(checksum 去重,已应用的跳过)。

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
6. **上线**:`backend-deploy`(`deploy.sh -b` 自动 apply;日志出现 `managed migrations applied: <你的文件名>`)。

## 关键点

- 列要 **nullable 或有默认**,旧行才不炸(R16 的 `significant`/`confidence` 就是 nullable)。
- runner 按 checksum 记录已应用迁移,**改已应用的迁移文件内容不会重跑**——要补改另写一个新迁移。
- 生产是 PostgreSQL,测试/CI 是 in-memory SQLite,本地 dev 也是 PostgreSQL。别给 `DATABASE_URL` 指向 sqlite 文件(代码有 JSONB/TIMESTAMPTZ 假设)。
- 迁移涉及敏感表(用药/基因/化验/CGM)→ 上线走 `safety-gate`。

## 应用机制(排错用)

`deploy.sh -b` → `backend/scripts/apply_managed_migrations.py`:扫 `migrations/managed/*.<dialect>.sql`,按 `schema_migrations` 表的 checksum 跳过已应用,新的按文件名顺序执行。`-b` 日志里 `managed migrations applied/skipped` 两行能看到结果。
