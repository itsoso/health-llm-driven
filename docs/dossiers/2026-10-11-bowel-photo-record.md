# Dossier: 排便记录与私有照片

| 字段 | 值 |
|---|---|
| slug | bowel-photo-record |
| 创建日期 | 2026-10-11 |
| 当前阶段 | G4 安全审查完成；等待发布 Gate |
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
Backend 与 Mobile 按计划分开写；已增加聊天附件菜单“排便记录”直达弹窗，关闭菜单且不走聊天图片发送。入口 RED（缺按钮）后 GREEN98 passed；私有上传相关新鲜回归56 passed / 2 PG-only skipped。父 run: docs/_generated/harness-runs/aa47ef58d1b7.jsonl。

## G3 测试
裁决: PASS（本地实现验证，不代替发布前完整 CI）。Backend RED 10 项行为失败已保存；SQLite 44 passed / 3 PG-only skipped；隔离 PostgreSQL 47 passed（含并发同 UUID 收敛/不同载荷409），受管迁移两方言2 passed。Mobile 6 个相关 suite 155 passed，tsc exit0；类型生成、System Map、Dossier consistency、diff check通过。
日志：/tmp/bowel-photo-red.log、/tmp/bowel-photo-sqlite-final.log、/tmp/bowel-photo-pg-final.log、/tmp/reva-bowel-mobile-final.log、/tmp/reva-bowel-tsc-final.log。


## G4 独立安全审查
裁决: GO。独立 morning_safety_review 审查源代码候选 09a293f64f83cee280afbef0f84b3d776b34c5d5（包含 be08913cf）。独立 Mobile 16 passed、SQLite 19 passed / 3 PG-only skipped、聊天入口1 passed，均 exit0；保留 PostgreSQL47 passed证据。明确 owner/subject/epoch、私有短效签名、人工确认、幂等与未知数据边界。
追加入口全套98 passed、tsc exit0；类型生成 --check通过。本地 iOS JS export exit0（仅构建验证，包含当前工作树既有饮食入口 WIP，不作为发布制品或精确提交验收）。
原图仍沿用既有账号删除时的私有目录清理；单条观察记录删除不等于照片擦除，本版不新增照片删除承诺。


## G5/G6 发布与验收
未部署，未发布 OTA；原失败发布保留，不能更换候选绕过。相机硬件实拍未验证。

## 发布整合补充：饮食记录入口与账号隔离
饮食已保存卡片新增“查看饮食记录”，打开现有 /diet 弹窗，合法 record_date 定位当日，无日期或非法日期回到当前日。109项卡片测试与类型检查通过，提交 abba1b168。
发布增量安全审查对 abba1b168 裁决 NO-GO：目标页 daily/frequent 缓存未绑定账号，会复用前账号数据。已补真实 React Query hook RED（4项失败）→ GREEN：daily/stats/frequent 键绑定 owner 与会话 revision，未登录禁用且手动 refetch 拒绝；敏感结果不持久化，inactive cache立即回收。读取绑定 subject/revision，晚到响应和 owner 不匹配拒绝。切号、退出、同账号新登录、旧持久缓存和常吃食物均有回归。
39项相关测试、tsc、System Map检查通过；日志 /tmp/reva-diet-owner-red.log、/tmp/reva-diet-owner-final.log、/tmp/reva-diet-owner-tsc.log。等待固定新候选独立重审及完整CI。
原 9c120 OTA attempt1 的 preclaim 失败证据保留；在此前已呈现的一次窄例外后，用户再次直接授权“部署和发布OTA”，独立 operational G4 GO 原 run38108049009 一次 attempt2。先收尾原候选，不能通过推新SHA绕过未完成OTA；attempt2再失败不得续行。
