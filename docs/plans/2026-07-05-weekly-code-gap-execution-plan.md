# 2026-07-05 本周计划对照与下一批执行计划

> 目标:对照 2026-06-29 本周发布计划、PRD/长期规划和当前代码,找出未闭环事项,形成下一批按优先级执行的计划。
> 代码快照:当前工作区在 `main`,但已有并发改动: `backend/app/api/agent.py`、`backend/app/services/inline_cards.py` 为 modified,`backend/tests/test_inline_cards_intake_dedup.py` 等为 untracked。本计划只记录现状,不假定这些改动已稳定上线。
> 2026-07-05 品牌裁决:遵循 Claude 已落地改动和用户确认,产品/AI 人格主名采用 `小巴`;历史计划里的 `阿衡` 视为待同步旧称,后续不再回滚到 `阿衡`。
> 2026-07-05 交互裁决:遵循 Claude 已落地改动和用户确认,Mobile 不再恢复底部四 Tab;`小巴` 对话是唯一主入口,`今日/记录/我` 作为二级能力从对话内入口进入,整体对齐支付宝「阿福」式 agent-native shell。

## 对照来源

- 本周计划:`docs/plans/2026-06-29-weekly-release-execution-plan.md`
- App Store MVP:`docs/plans/2026-06-28-app-store-mvp-release-plan.md`
- App Store final gate:`docs/plans/2026-06-29-app-store-final-submit-gate-plan.md`
- GenUI 契约:`docs/plans/2026-06-30-reva-genui-contract.md`
- 动态 UI 原子能力:`docs/specs/active/2026-06-29-agent-native-dynamic-ui-atomic-capabilities.md`
- Agent 操作面契约:`docs/specs/active/2026-07-02-agent-operable-module-contract.md`
- Intake intent router:`docs/plans/2026-07-04-intake-intent-router-implementation-plan.md`
- Phone-first auth:`docs/specs/active/2026-07-03-phone-first-auth.md`
- 长期路线图:`docs/PRODUCT_ROADMAP.md`
- 权威 PRD:`docs/prd/reva-personal-health-os-prd.md`

## 本次补充代码核对

- `mobile/app/(tabs)/_layout.tsx`:Phase 5 注释和实现均明确“移除底部 Tab Bar,小巴(chat) 成为主屏”,`tabBar={() => null}` 是当前架构事实。
- `mobile/app/(tabs)/index.tsx`:根路由 `/` 显式 `Redirect` 到 `/(tabs)/chat`,说明 Chat-first 不是临时样式,而是路由层产品决策。
- `mobile/components/common/BackToChatBar.tsx`:二级屏统一通过“返回小巴”回到主入口,与无底部 Tab Bar 架构匹配。
- `mobile/components/chat/BriefingStrip.tsx`:Chat 内“今日简报”进入 `/(tabs)/today`,承担原今日 tab 的入口职责。
- `mobile/app/(tabs)/record.tsx`:记录页是二级聚合页,顶部有 `BackToChatBar`,内部提供“说一句/拍一下/点一下”和高频记录入口。
- 漂移点:`mobile/app/(tabs)/__tests__/tabLayout.test.ts`、`scripts/check_app_store_release_pack.py`、`docs/release/app-store/submission-pack.md` 仍有“四 tab 可见/今日、小巴、记录、我”的旧发布假设,需要跟随单入口策略更新。

## 代码对照结论

| 领域 | 计划要求 | 当前代码观察 | 状态 | 下一步 |
|---|---|---|---|---|
| 品牌与发布一致性 | 新裁决:主名 `小巴`;交互主入口也是 `小巴` | `mobile/app.config.ts`、`mobile/constants/brand.ts` 已切到 `小巴`;旧计划/部分文案仍残留 `阿衡` 或四 tab 旧说法 | **P0:品牌与入口已定,需要防旧称/旧 IA 回流** | 不回滚小巴;同步旧 PRD/计划/系统地图/发布闸,把 `阿衡` 和“四 tab 可见”作为 stale public wording 检查 |
| Mobile 主入口 | 对齐阿福:单 agent 入口,能力藏在对话上下文和快捷入口里 | `_layout.tsx` 已 `tabBar={() => null}`;`index.tsx` 重定向 chat;二级屏用 `BackToChatBar` 回小巴 | **P0:代码方向正确,文档/测试/发布闸漂移** | 固化单入口架构;更新测试、release checker、App Store 文案,避免后续 agent 误恢复底部 tab |
| App Store final gate | final-submit 机器闸 + ready 截图 + demo/ASC 人审材料 | checker 仍要求 `今日 / 小巴 / 记录 / 我`;release pack 仍描述四个底部入口 | **P0 阻塞:发布材料与现 UI 不一致** | 改成“小巴单入口 + 今日简报/记录托盘/个人中心二级入口”文案后重截屏,再跑 final-submit |
| Today 主线 | Daily Artifact 是小巴首页里的关键可执行模块,不是独立 tab 入口 | Dynamic Today/DailyArtifact 代码存在;`BriefingStrip` 从 Chat 进入 Today 二级页 | 部分完成 | 把“今日”定义为小巴对话内的状态卡/简报条/二级详情,验收重点从底部 tab 改成“打开即看到该做什么” |
| Chat GenUI 图表 | 图表必须通用化,真数据,不能 ASCII/编数据 | 后端 `genui` 确定性图表、Mobile/Mac `reva-ui` 渲染、caps 已存在;覆盖 HRV/心率/睡眠等 | 基本完成 | 继续扩 `metric_grid/table/timeline/comparison/action_card`,并补 Web parity/端上 smoke |
| Chat 动态卡片交互 | 卡片要可确认、可修改、可执行、可反馈 | `renderCard`、`dispatchChatCardAction`、结果按钮已存在;但 action allowlist 仍是前端手写,与后端/Agent ops 注册表未同源 | 部分完成 | 让前后端 action allowlist 与 Agent ops registry 对齐;每个可见按钮必须有 dispatch 测试 |
| 饮食/用药意图 | 药物不能记成饮食;删除这一餐不能变新餐 | `intake_intent_classifier.py`、`MedicationDraftCard` 已有;`inline_cards.py` 当前 dirty,新增 dedup 测试 untracked | 部分完成但未稳定 | 稳定 classifier + tool_validator + inline cards;提交并验证 medication/supplement/diet/delete 四类 |
| 用药草稿动作 | 用药记录必须安全、可执行、低摩擦 | 后端用药草稿 action 现在 route 到 `/medications?draft=...`;`medications.tsx` 未看到读取 draft 参数 | **P0 体验断点** | 补用药 draft 参数预填/记录流,或改为明确的 manual-confirm 写入路径 |
| 拍照记餐 | 记录页拍一下应直接拍照识别 | `record` 进入 `/diet?capture=photo`;`diet.tsx` 会 `launchCameraAsync` | 看起来已实现 | 做真机/模拟器 smoke,防回归到只跳饮食页 |
| HealthKit | iPhone 自动同步,不手工同步 | 前台自动同步 hook/service 存在;服务端 consent/provenance 存在 | 已完成代码切片 | 真机权限、后台交付、App Store entitlement 仍需 RC 验证 |
| Watch | 腕上快速记录、短答、执行反馈 | Watch summary/quick record/voice food draft/ask endpoint 与测试存在 | 部分完成 | 真机签名验证;不承诺第三方 App 长按表冠唤醒,改为 complication/AppIntent/快捷入口 |
| Phone-first auth | 手机号登录注册,可改密码 | 后端 phone code、Aliyun SMS、Mobile login/settings、测试存在 | 基本完成 | 生产 SMS 配置、账号绑定和 App/Mac/Web 登录入口 smoke |
| LLM 成本与性能 | Admin 全局监控 + 每次 token + 端上透视 | Dossier shipped;Admin `/admin/llm-performance`;Mac/Web/Mobile profile 存在 | 已完成 | 继续加预算策略和异常告警,不是本批阻塞 |
| Agent 操作面 | 每个一等对象默认 Agent 可操作 | registry 与 CI 已有;spec 已挂账 waist/sleep/excretion create、supplement undo、goal、medical_exam list 等缺口 | 部分完成 | 排入 P1/P2,按对象补 CRUD/opt_out |
| 7 天健康运行时 | 未来 7 天日程化编排,低打扰执行 | rolling runtime spec 和部分 agenda/watch/today 实现存在;已补今日日内 time_driven 时间骨架 | 部分完成 | 继续推进日历/位置/药品/NFC/环境 IoT/失败原因自纠偏 |

## 新计划

### P0:先收敛小巴单入口可发布版本

1. **小巴品牌裁决落账**
   - 输入:用户确认“已经将品牌名从阿衡改为了小巴,要遵循这个决定以及所做的修改”。
   - 输入:用户确认“底部的四个Tab已经删掉,只保留小巴这一个入口,跟支付宝阿福保持一致”。
   - 决策:`小巴` 是 App 主名、AI 人格名、发布材料主名和 Mobile 唯一主入口;`阿衡` 与四 tab 可见均作为历史旧假设处理。
   - 执行:同步旧 PRD/计划/系统地图/App Store 文案/截图 runbook,把 `阿衡` 和“四 tab 可见”纳入 stale public wording gate。
   - 验收:`mobile/app.config.ts`、`APP_DISPLAY_NAME`、Chat header、App Store checker、release pack、截图文案均为 `小巴`,且不再承诺底部四 tab。

2. **固化小巴单入口 IA**
   - 保持 `tabBar={() => null}` 和 `/ -> /(tabs)/chat`。
   - `今日`:通过 Chat 顶部 `BriefingStrip` 和回答里的行动卡进入,二级页顶部保留“返回小巴”。
   - `记录`:通过 Chat 输入栏 `+`、Composer suggestion、记录托盘、拍照/语音入口进入,二级页顶部保留“返回小巴”。
   - `我`:通过 Chat 顶部更多菜单和必要设置入口进入,避免把低频功能摆到底部常驻。
   - 验收:冷启动首屏即小巴;无底部 tab 占高;二级页都有明确返回小巴路径;常用记录不超过 1 次点击或一句话。

3. **修正单入口测试和发布闸**
   - 更新 `mobile/app/(tabs)/__tests__/tabLayout.test.ts`:不再断言四个全局 tab 可见,改为断言 route segment 保留、tabBar hidden、`chat` initial route、二级入口可达。
   - 更新 `scripts/check_app_store_release_pack.py`:删除 `CURRENT_BOTTOM_NAV_TEXT`,新增 `CURRENT_AGENT_NATIVE_ENTRY_TEXT` 或等价检查,要求 release 文案描述“小巴单入口 + 对话内快捷入口”。
   - 更新 `docs/release/app-store/submission-pack.md`:把“今日、小巴、记录、我”改成“打开即进入小巴;今日简报、记录和个人中心从对话内进入”。
   - 验收:release checker 不再强制四 tab;截图 runbook 以小巴对话首屏作为第一张图。

4. **稳定摄入意图路由**
   - 合并并清理当前 dirty/untracked 摄入相关改动。
   - 必须覆盖:
     - `记录午餐吃了牛肉面` -> diet draft/record。
     - `记录刚吃了替普瑞酮` -> medication draft,绝不 diet。
     - `吃了鱼油` -> supplement,绝不 diet。
     - `删除这一餐` / `我刚才不小心删除了` -> diet management,绝不新增饮食。
     - 已记录后不再冒同类空草稿。

5. **修用药草稿可执行性**
   - 二选一:
     - A. `/medications?draft=medication&name=...` 在用药页预填并引导确认。
     - B. 后端发 manual-confirm write intent,前端 dispatcher 走安全写入。
   - 用药属于 never_auto,不做静默自动写;但不能让用户点了只进入空列表。

6. **动态卡片动作闭环**
   - 每个服务端可见 action 必须在 Mobile dispatcher 有对应处理或明确 route.open。
   - 前端 allowlist 与后端 `agent_ops_registry` 建立校验,避免按钮被过滤或无效。
   - 回答卡片下方四个动作按钮继续保留:加入今日计划 / 保存记忆 / 生成记录 / 继续追问,但需要保证成功后有 toast、状态、缓存刷新。

### P1:本周可用版体验完善

7. **小巴首屏信息架构复核**
   - 首屏不做功能列表,只保留三类信息:小巴状态/今日简报/最可能要做的一件事。
   - 高频入口用阿福式轻量 chip 或输入栏工具承载:拍照记餐、说一句、饮水、用药、体重、更多。
   - 验收用用户动线:打开 App -> 看到今日重点 -> 执行/跳过/追问 -> 记录饮食/用药/运动 -> 自动回到小巴并更新进度。

8. **拍照记餐真机 smoke**
   - 从记录页 `拍一下` 直接进相机,拍照后生成饮食草稿,确认后更新饮食进度。
   - 从 Chat 输入栏拍食物,也应生成可编辑饮食卡,不是体检导入误路由。

9. **App Store / QR RC**
   - 品牌、单入口 IA、发布文案稳定后重跑模拟器截图,必要时真机截图。
   - 跑普通 release pack 与 final-submit preflight。
   - 生成默认二维码发版包;App Store 只在手工指定时走提交。

10. **HealthKit / Watch 设备验证**
   - iPhone 真实 HealthKit 授权、前台自动同步、撤权、无数据降级。
   - Watch 真机 summary、quick record、diet voice、ask 安全门、action complete/skip/snooze。

11. **手机号登录生产验证**
    - 确认 Aliyun SMS 配置、生产环境 503 fail-loud、短信成功路径。
    - 验证 `itsoso@126.com` 与 `13486176286` 登录同一个 user id=3。

### P2:长期规划继续推进

12. **Agent 操作面补洞**
    - 补 `waist/sleep/excretion` create。
    - 补 supplement 打卡 list/update/delete/undo。
    - 补 goal Agent CRUD。
    - 补 medical_exam 报告级 list。
    - 补 intervention_cycle 历史/调整/取消。

13. **扩展 Dynamic UI 组件目录**
    - `metric_grid`、`table`、`timeline`、`comparison`、`alert_list`、`action_card`。
    - 规则:LLM 只选组件/叙事,数据仍由确定性代码填充。

14. **滚动 7 天健康运行时**
    - 已完成 Slice: 今日时间线补晨起/午间/下午/晚间/睡前 `time_driven` 低打扰系统时刻卡;已有同窗口同域真实项时自动让位。
    - Calendar-aware 工作间歇、饮水、午休、运动、晚间建议。
    - 药品/NFC/固定位置确认先做 spec + 可行性验证,不直接承诺。
    - 失败原因驱动自纠偏,减少打扰而不是增加提醒。

## 建议验证命令

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_intake_intent_classifier.py \
  backend/tests/test_inline_cards_runtime_agenda.py \
  backend/tests/test_tool_validator.py \
  backend/tests/test_agent_ops_registry.py \
  -q --no-cov

cd mobile && ./node_modules/.bin/jest --runTestsByPath \
  __tests__/app-config.test.ts \
  app/(tabs)/__tests__/tabLayout.test.ts \
  app/(tabs)/__tests__/chat.test.tsx \
  app/(tabs)/__tests__/recordEntry.test.tsx \
  components/chat/cards/__tests__/registry.test.tsx \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  services/__tests__/chatCardActions.test.ts \
  --runInBand

cd mobile && npx tsc --noEmit
python3 scripts/check_app_store_release_pack.py
python3 scripts/check_doc_drift.py
```

## 执行顺序

1. P0-1/P0-2 小巴品牌与单入口 IA 先收敛。
2. P0-3 修正单入口测试、发布闸和 App Store 文案。
3. P0-4/P0-5 摄入意图和用药草稿闭环。
4. P0-6 动态卡片 action 闭环。
5. P1-7/P1-8 小巴首屏动线和拍照记餐 smoke。
6. P1-9 发布二维码 RC。
7. P1-10/P1-11 HealthKit/Watch/手机号生产验证。
8. P2 长期能力分批推进。

## 2026-07-05 执行回写

- P0-1/P0-2 已完成:Mobile 继续保持小巴单入口,`/(tabs)` 冷启动进入 `chat`;底部 Tab Bar hidden 契约已由 `tabLayout.test.ts` 钉住。
- P0-3 已完成:App Store release gate 不再要求 `今日 / 小巴 / 记录 / 我`;发布文案改为“打开即进入小巴,今日简报、记录和个人中心从对话内进入”。
- P0-4/P0-5 已完成:摄入 classifier 保持 diet/medication/supplement/water/diet_management 分流;用药草稿 route 携带 `dose`;Mobile 用药页支持从小巴草稿确认写入用药清单并记录一次已服用。
- P0-6 已核对完成:当前 Chat 卡片 action 集合仍为 `agenda.complete`、`diet_record.create`、`route.open`、`ui.inline.expand` 等既有受控动作,Mobile dispatcher/registry 测试通过。
- P1-7/P1-8 已完成代码闸验证:小巴首屏保留无底部 Tab 的 compact composer、空对话固定“拍照记一餐”chip;记录页“拍一下”直达 `/diet?capture=photo`;饮食页 `capture=photo` 生成待确认饮食草稿且不自动入库。移动端 smoke: `chat.test.tsx`、`recordEntry.test.tsx`、`dietCapture.test.tsx` 通过。
- P1-9 已完成二维码 RC:release pack、iOS App Store preflight、doc drift、移动端 focused smoke、TypeScript 均通过;基于 `f4ac7f14` 构建 `20260705-124315-f4ac7f14`。ad-hoc 导出因 `life.executor.health`、Watch app、Watch extension 缺 ad-hoc profiles 失败,脚本回退 development 导出成功并上传。公开安装页: `https://health.executor.life/mobile-install/ios/20260705-124315-f4ac7f14/install.html`;manifest/IPA 均 HTTP 200,manifest bundle id 为 `life.executor.health`。本批未补拍 App Store-ready 截图集,final-submit 截图 gate 仍需单独跑。
- P1-10/P1-11 已完成自动化与只读生产验证:后端 HealthKit/Watch/手机号登录 focused tests `136 passed`;Mobile HealthKit foreground sync + auth/login tests `33 passed`;Watch Swift core tests `61 passed`;QR IPA 内主 bundle 为 `life.executor.health`、display name `小巴`、包含 `com.apple.developer.healthkit=true`,并嵌入 `life.executor.health.watchkitapp` 与 `life.executor.health.watchkitapp.watchkitextension`。生产只读检查显示 SMS dev echo 关闭、PNVS 通道已配置,user id=3 同时绑定 `itsoso@126.com` 与 `+8613486176286`,手机号已验证且账号 active/approved。未擅自触发真实短信;真机 HealthKit 授权/撤权、Watch 表上操作和短信实发仍需设备交互验收。
- 待继续:App Store final-submit 截图集补拍与人工审核;真机 HealthKit/Watch/SMS 实操验收;P2 Agent 操作面补洞。
