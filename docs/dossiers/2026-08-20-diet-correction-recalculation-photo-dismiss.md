# Dossier: 饮食修正重算与餐食大图滑动关闭

| 字段 | 值 |
|---|---|
| slug | `diet-correction-recalculation-photo-dismiss` |
| 创建日期 | 2026-08-20 |
| 当前阶段 | G5 已通过；G6 真机用户路径待确认 |
| 状态 | deployed_device_smoke_pending |
| 负责 | Codex + 用户 |
| 反馈环 | Backend focused tests + Mobile Jest/TypeScript + production OTA after Gates |

## S0 · 用户需求（逐字）

> 点击调整记录，修改食物的内容。比如把1碗改成两碗，那么在保存的时候要重新计算热量。当前只是修改了内容，但是没有修改和重新计算真实的营养物质和热量，要做这个优化。点击图片，展开午餐图，用手滑一下，图片应该自动消失，而不是再点击那个叉号再消失。要优化这个交互。

- 用户：在小巴聊天中查看、修正已记录餐食的 Mobile 用户。
- 当前绕过：食物改动后还要手工同步四项营养；大图只能点关闭按钮。

## S1 · Discovery

- `mobile/components/chat/cards/RecordQualityCard.tsx`：当前调整器把新食物描述与旧营养输入一起直接 `PUT`，没有重估步骤。
- `mobile/services/diet.ts`：现有调整路径只有普通 owner-scoped `updateDietRecord`，客户端分两次“估算→PUT”会留下并发覆盖和半完成窗口。
- `backend/app/api/diet.py`：普通更新只会清空不可信旧营养，不会重算；现有文字估算接口也尚未复用食物识别 sanitizer。
- `mobile/components/chat/cards/DietDraftCard.tsx`：`MealPhotoGallery` 仅支持横向翻页和关闭按钮。
- 硬约束：营养仍是估算而非测量值；估算失败不得写入半成品；横向翻图不得被纵向关闭手势误伤；保留关闭按钮。

## G1 · 准入裁决

- first_class_objects：`ExecutionEvent`、`HealthTwin`（纠正后的 `DietRecord` 是其饮食事实输入）。
- core_loop_step：Capture → corrected record → HealthTwin/下一餐建议。
- target_surface：Mobile；source of truth：Backend/PostgreSQL `diet_records`。
- safety_level：privacy-sensitive health write；autonomy：`manual_confirm`。
- spec_required：yes（用户可见行为 + 健康数据写路径）。
- smallest_end_to_end_slice：聊天内改食物 → 一条服务端命令安全重估并原子更新 → 完整回读刷新；餐食大图纵向滑动关闭。
- **裁决：PASS**。用户已明确要求实施。

## S2 · PRD

- 链接：`docs/prd/2026-08-20-diet-correction-recalculation-photo-dismiss.md`
- 非目标：不宣称营养为实测；不改图片存储/分享；不做自动保存或后台静默修正。

## S3 · 规划

- 链接：`docs/plans/2026-08-20-diet-correction-recalculation-photo-dismiss.md`
- 发布路由：Backend 先部署；纯 JS/TS Mobile 改动后走 production OTA。

## G2 · 可行性 + 安全压测

- 方案：新增 owner-scoped 原子重算命令。服务端先读取版本快照，在不持行锁时估算并清洗，随后重新加锁/CAS 校验，在一个事务内写入新描述与五项营养；估算失败或并发冲突均零写入。稳定 operation key + request digest 使丢响应重试可取回已提交结果，不重跑模型。
- 手势：只接管明确纵向滑动，横向仍交给分页 `ScrollView`，叉号保留。
- 硬阻断已进入验收：禁止沿用旧营养、禁止 LLM 原始 totals/健康提示直写、禁止估算失败后只改文本、禁止含酒文本重算时清空或伪造标准杯。
- 待拍板分叉：无。
- **裁决：PASS**。用户的保存动作是写入确认。

## S4 · 研发任务分解

- [x] T1 新增服务端原子重算接口，复用 sanitizer/calibration，补 fiber、CAS、action seed revision 与安全错误语义。
- [x] T2 聊天内调整器在食物变化时只调用重算接口，完整替换五项营养；失败零写入；409 不重放旧 revision；失效旧 progress/下一餐派生内容。
- [x] T3 餐食大图加入纵向滑动关闭且不破坏横向翻图。
- [x] T4 focused tests、OpenAPI 生成类型、TypeScript 与 G4 独立安全评审完成。
- [ ] T5 已从当前 `origin/main` 依次部署 Backend 与 Mobile OTA；待真机完成生产用户路径验证后关闭。
- 并发检查：已检查开放 PR，未发现同一修正链路的在途 PR。

## S5 · 实现

- 委托：`health-harness-orchestrator`（同一父 run）。
- Backend：owner-first 原子重算、required nullable revision、幂等回执/CAS、五项营养权威回读、含酒修正 fail-closed、action seed revision/fiber。
- Mobile：食物变化只走重算命令；同语义请求复用 operation key；409 保留输入且禁止旧 revision 重试；旧 progress/建议失效；餐食大图纵向滑动关闭并保留横向翻页/X/Android back。
- 契约：Mobile 与 Frontend OpenAPI 生成类型已同步。
- commit：本 feature commit（基于 `origin/main@4140bb7a3` 的干净集成候选）。

## G3 · 测试闸

- Backend focused 回归：最新远端主干干净集成后 `280 passed`（`test_diet.py`、`test_post_record_quality.py`、`test_agent_executor_food_vision.py`）。
- PostgreSQL 语义闸：重算相关 `38 passed`，覆盖真实 `FOR UPDATE`/双 Session 并发路径及扩展酒精 fail-closed 矩阵。
- Mobile：最新远端主干干净集成后 3 suites / `120 passed`；`tsc --noEmit` PASS；目标 ESLint `0 errors`（仅既有 9 warnings）。
- 契约/治理：OpenAPI generated types check、Ruff、`py_compile`、Dossier consistency `111/111`、System Map、`scripts/validate.py` blocking checks、`git diff --check` 全部 PASS。
- **裁决：PASS**。

## G4 · 安全闸

- 触发：健康数据写路径 + LLM 营养候选。
- 独立 Mobile/UX slice GREEN；Backend safety reviewer 与跨端最终 reviewer 对最新 diff 均未发现 BLOCKER/HIGH。
- **裁决：PASS / GO**。

## S6–S8

- 已在基于 `origin/main@4140bb7a3` 的独立干净工作树重放本 feature；远端新增饮食食材披露改动被保留，Backend/Mobile/PostgreSQL/类型/System Map 全部复测通过。
- feature commit `272782b33` 已进入主干；发布使用的精确主干为 `994c5665aef34fcf092679ba99edc12b7adfa9b8`，其 GitHub CI run `32356968903` 完成且结论为 success。

## G5 · 部署健康闸

- Backend 通过唯一入口 `./deploy.sh -b` 从干净 `main` 发布到生产；数据库备份、237 表恢复演练、站外加密归档哈希/HMAC、依赖锁、完整 runtime schema、runtime-only KB guard/staged contract、Skills manifest 均通过。
- 生产远端 revision 精确为 `994c5665aef34fcf092679ba99edc12b7adfa9b8`；`health-backend`、Celery worker、Celery beat 均为 active；重复健康评分为 `60/60 PASS`。
- 新端点 `POST /api/v1/diet/records/{record_id}/recalculate-nutrition` 在生产返回预期未授权 `401`，而非旧进程/未注册路由的 `404`；健康端点报告 API、PostgreSQL、Redis、Celery 正常。
- iOS production OTA 使用同一精确 source 发布到 runtime `1.3.3`；EAS group `d1d15b9c-e3bf-4190-be81-f96e3d16d504`、iOS update `01a01fe0-2dc2-74d6-970b-093eab295ff9`。独立 `update:view` 回读确认 branch、runtime、platform、commit 与发布记录一致。
- **裁决：PASS**。

## G6 · 生产用户路径验证

- 机器侧已证明 Backend 新路由生效且 OTA 对目标 production/runtime 可达。
- 尚未以真实用户记录执行“修改食物份量 → 服务端重算五项营养 → 保存后完整回读”，也尚未在真机验证餐食大图纵向滑动关闭与横向翻页不冲突。为避免修改真实健康数据或把发布成功冒充用户体验成功，本 Gate 保持 **PENDING**。
- 真机验证步骤：彻底关闭并重开 App 应用 OTA；选择可安全修改的测试餐食，将份量从 1 改为 2，确认热量/蛋白质/碳水/脂肪/膳食纤维共同变化且刷新后保持；打开餐食大图，纵向滑动关闭，再确认横向多图翻页仍正常。
