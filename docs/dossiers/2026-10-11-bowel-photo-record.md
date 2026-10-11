# Dossier: 排便记录与私有照片

| 字段 | 值 |
|---|---|
| slug | bowel-photo-record |
| 创建日期 | 2026-10-11 |
| 当前阶段 | S5 实现 |
| 状态 | building |
| 负责 | root |
| 反馈环 | Mobile Jest / PostgreSQL / simulator |

## S0 用户需求
> 我发现还要加一个排便的记录和拍照

## S1 Discovery
已有 backend/app/models/excretion.py、backend/app/schemas/excretion.py、backend/app/api/excretion.py；Mobile 未有排泄页面。复用 backend/app/api/upload.py 的 medical 私有 owner 存储与 backend/app/services/private_uploads.py 的短效签名。现有记录页和 Expo modal 支持入口；相机权限已有。

## G1 准入
裁决: PASS。映射 HealthTwin、ExecutionEvent 与观察证据闭环；manual_confirm。用户直接要求实现，既有授权支持完成可审查代码。

## S2 PRD / Spec
- docs/prd/2026-10-11-bowel-photo-record.md
- docs/specs/active/2026-10-11-bowel-photo-record.md

## S3 Plan / G2
裁决: PASS。复用现有 API/私有上传，照片不进模型，状态未知保持未知；nullable schema 兼容旧记录，提交幂等避免重复。无待拍板产品分叉。
- docs/plans/2026-10-11-bowel-photo-record.md

## S4/S5
Backend 与 Mobile 按计划分开写；父 run: docs/_generated/harness-runs/aa47ef58d1b7.jsonl。

## G3 测试
裁决: PASS（本地实现验证，不代替发布前完整 CI）。Backend RED 10 项行为失败已保存；SQLite 44 passed / 3 PG-only skipped；隔离 PostgreSQL 47 passed（含并发同 UUID 收敛/不同载荷409），受管迁移两方言2 passed。Mobile 6 个相关 suite 155 passed，tsc exit0；类型生成、System Map、Dossier consistency、diff check通过。
日志：/tmp/bowel-photo-red.log、/tmp/bowel-photo-sqlite-final.log、/tmp/bowel-photo-pg-final.log、/tmp/reva-bowel-mobile-final.log、/tmp/reva-bowel-tsc-final.log。


## G4 独立安全审查
待评审。

## G5/G6 发布与验收
未部署，未发布 OTA；原失败发布保留，不能更换候选绕过。相机硬件实拍未验证。
