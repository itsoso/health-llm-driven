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

## 2026-09-03 Correction Block · 已记录餐食缺少可发现的修正入口

### 触发

用户提供真机截图并指出：已记录餐食卡写着“可在记录页继续修正”，但卡面和紧邻操作区只有“编辑分享图 / 分享正文”，没有可发现的饮食修正入口；同时“午餐已记录”与底部“确认后才写入”存在终态语义冲突。

### 裁决与范围

- 回退阶段：S5；沿用本 Dossier 和既有原子重算写路径，不新建数据模型或写权限。
- G1：PASS。既有 `DietRecord -> HealthTwin` 核心闭环的可用性修复；用户本次明确要求实施。
- G2：PASS。主入口只展开现有 owner-scoped 修正编辑器，最终仍需用户点击“保存修正”；缺少记录身份或安全 seed 时不提供伪可用入口。
- 最小切片：已记录饮食卡 → 明显的“继续修正本餐” → 就地编辑 → 人工保存 → 卡面更新。
- UI 收敛：修正提升为主操作；分享降为次级；移除卡内重复的社交分享宣传块；已记录态统一为“已计入今日饮食 / 营养为估算，可继续修正”。
- 发布授权：本 correction block 不继承 2026-08-20 的历史发布授权；本轮不 commit、push、deploy 或 OTA。

### 待验证

- [x] Mobile 入口可见、点击即展开、保存后收起并刷新卡面。
- [x] Backend 新生成的已记录饮食卡同时携带 owner-matched `record_id`、revision 与修正 seed；不再依赖易丢失的通用 action bar 才可修正。
- [x] 旧卡即使仍携带“确认后才写入”，在 recorded 状态也会统一投影为“营养为图片估算，如有偏差请继续修正”。
- [x] TDD、TypeScript、目标 lint、Backend owner-isolation/重算回归、System Map/doc drift。
- [x] 仓库级 Dossier consistency：2026-09-05 对 122 份 Dossier 复核通过。
- [x] 固定提交独立 G4 safety/privacy review；此前 G4 不自动覆盖本次新入口。

### 2026-09-03 实现与验证证据

- Mobile：卡片内新增 52pt 一级入口“继续修正本餐”，直接展开既有 `DietRecordAdjustEditor`；缺少正整数记录 ID 或安全修正 seed 时 fail-closed。通用 action bar 的重复修正按钮在该卡型隐藏。
- UI/表达：移除“今日饮食打卡 / 小巴生成”重复宣传块；已记录状态改为“已计入今日饮食”；下一步改为“接下来 + 具体动作 + 依据”；分享入口改为“制作分享图 / 分享文字”；已记录态不再显示待确认写入文案。
- Backend：`post_record_quality` 与上下文餐食照片自动记录卡均把修正 seed 复制到 card data；后者在生成 seed 前验证 `record.user_id == current_user_id`，revision 仍来自当前记录。
- RED：Mobile focused 首轮 `5 failed, 163 passed`，失败点与缺入口/旧表达完全对应。
- GREEN：Mobile focused `2 suites / 169 passed`；`npx tsc --noEmit` PASS；目标 ESLint `0 errors`（测试文件 9 个既有 warning）；design token ratchet PASS。
- Backend：`test_post_record_quality.py + test_agent_executor_food_vision.py` 共 `124 passed`；重算、owner-first、CAS、幂等与失败零写入子集 `39 passed`。
- 治理：`py_compile`、`git diff --check`、System Map、mobile-nav、doc-drift PASS。
- LLM change gate：确定性 invariants `12/12`、health core `50/50`、trajectory `12/12`、goldens `9/9` PASS；2026-09-05 使用隔离进程与线上 TokenPlan 配置补跑 live orchestrator `5/5` PASS，平均质量分 0.96。
- 仓库级 Dossier consistency 当前由 `2026-08-29-app-review-medical-citations.md` 的 G6 判定冲突、`2026-09-03-agent-perceived-latency.md` 缺 G1 裁决阻断；两者属于其他在途改动，本切片未修改。
- 发布边界：本轮未 commit、push、deploy 或 OTA。固定提交独立 G4 与 live LLM gate 完成前不得发布。

## 2026-09-03 Correction Block · 分享照片编辑与海报预览体验

### 触发

用户提供两张 iOS 真机截图并指出：照片编辑器与分享预览 UI 层级、留白和操作表达较差；两个全屏步骤都缺少符合 iOS 习惯的滑动取消/返回。

### Quick Flow 裁决

- 回退阶段：S2/S3 合并 tech-spec；沿用现有分享资源生命周期、图片隐私遮挡和系统分享边界，不新增数据模型、API 或写权限。
- G1：PASS。目标用户是已记录餐食并准备分享的 Mobile 用户；命中 Capture → Review/Share 闭环；最小切片是照片编辑 → 海报预览 → 保存/分享/返回。
- G2：PASS。使用左缘右滑返回，避免与照片区域的拖动裁剪、双指缩放和隐私涂抹冲突；滑动调用与顶部返回相同的清理/确认路径，不允许绕过未保存编辑确认或在图片处理中强行退出。
- UI 目标：修复状态栏/标题冲突；五项编辑工具单行等宽呈现；明确“调整照片”和“分享这餐”两个阶段；海报预览顶部对齐并可在小屏滚动；公开分享前保留简洁隐私提醒；主按钮突出“生成分享图/分享”，保存与仅分享文字降为次级。
- 非目标：不改变营养估算、海报数据、相册权限、系统分享结果判断或服务端饮食记录。
- 发布授权：本 correction block 不继承历史发布授权；本轮不 commit、push、deploy 或 OTA。

### 验收与 Gate

- [x] 两个页面均支持从屏幕左缘右滑，达到距离/速度阈值后执行与顶部返回相同的取消路径；反向、纵向、双指和非边缘手势不误触。
- [x] 图片处理中禁止滑动退出；有未保存编辑时滑动仍触发丢弃确认。
- [x] 编辑工具保持原有旋转、遮挡、撤销、重做、重置能力与无障碍名称，视觉上单行不换行。
- [x] 海报预览消除大段顶部留白，小屏可滚动；分享、存图、文字分享和失败恢复语义不变。
- [x] Mobile RED/GREEN、TypeScript、目标 ESLint、design token、System Map/doc drift。
- [x] 固定提交独立 G4 privacy review；未发现新增的外发、越权读取或绕过取消确认路径。

### 2026-09-03 实现与验证证据

- 交互：新增复用的 `SwipeBackSurface`，左侧 28pt 内开始的单指触摸从开始阶段即保留给返回手势，避免被图片原生手势先行抢占；只有方向与距离/速度达标的右滑才返回，其他触摸回弹且不触发取消。取消动作仍进入原有确认或异步资源清理函数，照片 apply 阶段禁用。
- 照片编辑 UI：深色状态栏与安全区统一；标题改为“调整照片 / 裁剪与隐私处理”；隐私提醒收为轻量胶囊；旋转、遮挡、撤销、重做、重置改为单行图标工具；视口提供随模式变化的操作提示；主操作明确为“生成分享图”。
- 海报预览 UI：标题改为“分享这餐”，增加生成完成状态；海报从顶部开始并置于可滚动容器；加入发布前隐私复核；分享海报、存到相册、仅分享文字重新分层；失败态表达与按钮层级同步收敛。
- RED：首轮 focused 测试按预期 `7 failed, 34 passed`，失败覆盖新视觉表达、滑动入口和文字分享命名。
- GREEN：focused `2 suites / 41 passed`；后续按真实 `PanResponder` 释放阶段（`numberActiveTouches = 0`）补强回归后，修复前 `3 failed / 42`、修复后 `2 suites / 42 passed`；完整相关回归 `9 suites / 164 passed`；`npx tsc --noEmit`、目标 ESLint、design token ratchet、`git diff --check` 均 PASS。
- 治理：System Map、mobile navigation graph、doc drift 全部 PASS；此次未改变生成器覆盖的架构结构。
- 模拟器视觉证据：登录态下从 Chat“更多操作”进入“饮食记录”，打开真实餐食照片编辑器；确认新标题、隐私提醒、单行五项工具与主按钮均可见。首轮发现全屏 Modal 顶部安全区为 0，标题侵入状态栏；加入“当前上下文 inset + 启动窗口 inset 取较大值”后重新打包，截图确认标题完整避开动态岛/状态栏。有改动时点击返回可见“放弃图片编辑？”并可选择继续编辑。
- 模拟器补充证据：Expo 开发客户端 Reload 后虽执行到 `RootLayout`、登录态与路由，但 Fabric surface 丢失；改由 Xcode 增量构建重新安装后恢复正常，确认问题属于本地开发容器生命周期而非业务页面。真实登录态下重新走通 Chat → 饮食记录 → 午餐照片编辑 → 生成分享图，截图确认安全区、单行工具、生成完成状态、海报顶部对齐、隐私提示与按钮层级；未触发系统分享或任何外发。
- 手势补充修复：模拟器探针确认左缘触摸被正确接管（起点 4pt、单指），同时发现 `onPanResponderRelease` 的真实语义是活动触点归零；旧完成判定因此会拒绝本来合格的手势。测试先改为释放阶段 0 触点并稳定 RED，再把“单指资格”限定在开始/移动阶段，释放仅按已记录的左缘起点、方向、距离/速度裁决。
- 模拟器剩余边界：当前 Computer Use 拖拽只产生 touch start/release，释放位移固定为 `dx = 0`，无法生成连续 touch-move，因此不能把这次自动化拖拽冒充实体侧滑通过。代码级完成路径、脏编辑确认、apply 禁用与清理均已由真实释放语义单测覆盖；发布前固定提交 G4 与真机/可产生 touch-move 的执行器复核仍保持待办。
- 发布边界：本轮未 commit、push、deploy 或 OTA。

## 2026-09-04 Correction Block · Chat 主壳补充饮食记录入口

- 触发：模拟器登录后，为复核已保存餐食的修正与分享流程，仍需在大量历史对话中反复搜索；Chat 主壳“更多操作”没有稳定的饮食记录入口。
- G1/G2：PASS。复用既有 owner-scoped `/diet` 页面和读写路径，不新增数据模型、接口、自动写入或医疗判断；最小切片为“更多操作 → 饮食记录 → 既有餐食列表”。
- RED：`app/(tabs)/__tests__/chat.test.tsx` 新增入口测试，首轮 `1 failed, 53 passed`，失败原因为菜单中不存在“饮食记录”。
- 实现：在 Chat “更多操作”中加入“饮食记录”，关闭菜单后打开既有 `/diet`；副标题同步收敛为“记录、分享与个人中心”。
- 模拟器：真实打开 Chat“更多操作”，确认“饮食记录”入口可见并成功进入 owner-scoped 饮食页，再从既有餐食打开照片编辑器。
- 分享页追加修复：模拟器发现全屏编辑器标题侵入状态栏，新增启动窗口安全区回退；发现左缘触摸可能先被图片手势拿走，改为左侧 28pt 单指从触摸开始即保留，仍只允许合格右滑触发统一取消路径。
- 新鲜验证：Chat + 完整饮食组件 `9 suites / 164 passed`；`npx tsc --noEmit`、目标 ESLint、design token ratchet、System Map、mobile-nav、doc drift 全部 PASS；导航生成物已同步新增的 Chat → diet 边。
- 补充修复：发现手势释放阶段活动触点为 0，而旧实现仍要求 1，导致实体侧滑无法完成；测试先按真实释放语义复现 `3 failed / 42`，修复后 focused `42/42`、完整相关回归 `164/164`。
- 模拟器：通过 Xcode 干净构建绕过开发客户端 Reload 的 Fabric surface 丢失，已补齐海报预览截图与脏编辑退出确认；Computer Use 拖拽不产生 move 位移，实体侧滑仍保留为真机/可产生 touch-move 执行器复核项。
- G4：固定提交独立 privacy review 已完成；仓库密钥扫描、owner guard/失败零写入 427 个 Backend 用例、分享编辑与返回 42 个 Mobile 用例、Chat 54 个用例均通过。
- 发布边界：本轮不 commit、push、deploy 或 OTA。

## 2026-09-05 · 固定本地候选

- 经用户授权，本轮饮食修正入口、分享编辑体验与关联回归已随本地提交 `b9063c441` 固定。
- 2026-09-05 独立 G4 与真实 TokenPlan live gate 已通过；push、目标 SHA CI、OTA 与精确商店候选仍按各自 Gate 独立执行。
