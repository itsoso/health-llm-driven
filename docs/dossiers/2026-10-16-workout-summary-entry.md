# 运动记录入口与跑后总结回看

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification / G4 review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

- 日期：2026-10-16
- 状态：S5 实现与验证中；尚未发布
- Controller：health-harness-orchestrator；overlay：safety-gate

## G1 Scope admission

裁决: PASS。恢复现有运动回看入口及完整口语查询，不新增权限或健康写入。

## 问题与准入

用户截图显示聊天“更多操作”和个人中心缺少运动入口。跑后总结弹出后，离开就难以再次打开。本次恢复现有运动记录与详情的可发现性，不引入新的健康建议或自动生成行为。

## 实现范围与根因

- 聊天更多操作、个人中心“复盘与计划”增加固定“运动记录”入口。
- 列表按原有记录 ID 打开详情，可反复进入；提示可查看训练详情与已保存总结。
- 详情 hook 原先忽略接口已返回的 post_workout_analysis，额外缓存读取失败时总结消失。优先使用已存内容，仅进行缓存读取，失败显式提示并保留已存内容。
- 不改健康写入、设备同步及模型生成接口，不读取真实健康记录，不运行真实模型评测。

## 验收与证据

- RED：聊天与设置入口两个测试均在修改前失败（/tmp/reva-workout-entry-red.log）。
- G3：147 项相关 Jest 回归、TypeScript、System Map 和 diff-check 通过；包含重复入口、同一详情重开、缓存失败保留、账号/运动切换隔离。
- 证据：/tmp/reva-workout-all-tests.log、/tmp/reva-workout-types.log、/tmp/reva-workout-map.log。
- G4、安全边界、完整 CI、精确 SHA 后端与 OTA 回执：待完成，不能以本地测试替代。
- iOS 模拟器验收与设备 OTA 生效尚未验证。

## 发布授权

沿用本会话统一发布及改完默认部署、OTA 的授权。不备份，不启动第二发布者，不重放旧候选发布流程。

## 交付检查点

- 候选：be332385228e1390b7e4b9d2b6154bf162fe2b67；本地独立 G4 GO。
- Mobile 全量：357 suites、3693 passed、1 skipped；类型与导航图检查通过。
- 旧候选本地 CI-mode 发布不变量 3983 项无失败，但 dossier 格式检查失败；已补齐结构并通过一致性检查。追加修复后的新候选仍需完整 CI。
- 外部 Web 操作 b6dd746e9c404d50ad28ea0af5616ca5 已有终态、锁释放；b294 后端与服务正常。但发布者归属/交接尚未确认，已询问用户。不能用锁释放代替交接。
- 暂未 push，精确远端 CI、后端、OTA 均未开始；新候选 wrappers 仅准备，不执行旧流程。
- React Native Web 实际列表组件合成预览验证了点击路由；不代表 iOS 原生候选或真实账号验收。
- 详细状态：docs/reviews/2026-10-16-workout-summary-entry-release-receipt.json。

## 追加：口语倒装查询

用户补充截图：“刚才对我的运动做下分析”被未解析范围拦截。已在合成认证身份下复现三种完整倒装句失败（3 failed / 22 passed）。现有语法只支持前置分析动词，缺少“刚才对本人运动做下分析”的完整读请求形式。

新增完整匹配的后置分析语法，复用现有 OwnedReadScope，当地当天本人 workout 候选范围不变；不丢弃其他主体、引用、否定、额外日期、同步或写入约束。截图原句通过真实 Gateway、合成数据库查询与回复保存链路验证，含单次/批量读取和有/无记录。

SQLite 相邻回归 170 passed；PostgreSQL 独立验证 170 passed、测试库正常停止。旧 be332 候选 CI 与 wrappers 不可用于追加修改后的发布；需绑定新候选重审与完整 CI。不做真实模型评测或读取真实健康数据。

## 追加：症状误作餐食与排队显示

用户补充截图原句“记录下来，稍微有点拉肚子，跟昨天晚上吃海鲜有一定的关系。”被误送入餐食估算。需求准入仍为现有本人记录修复，不增加健康写权限；仅记录用户自述，食物关联不升级为确定病因。

排队状态专项检查未发现状态残留；已证实 UI 将 server_busy_queued 的 interrupted 状态当红色失败。仅仍有队列且可恢复时改为 active 展示，真实超时失败仍保持 error。RED 1 failed，GREEN 聊天78项及TypeScript通过；队列状态机专项7项通过，未更改重试/超时/取消逻辑。

新范围使用相同 Harness trace；待后端验证、整合候选G4及新CI。所有旧候选wrappers禁止用于最新代码发布。

症状根因补充：utterance_intent_classifier 症状词表缺少“拉肚子/腹泻”，导致饮食关键词抢占。补齐词表后，其他食物关联也回到症状普通处理；只有封闭且明确的本人记录请求授权确定性写入。精确截图保留整句自述，历史餐次不变，无模型调用。真正午餐记录含附带症状仍可保留饮食意图；否定、引用、第三人、咨询不自动记录。SQLite 症状及分类回归979项通过，最终PG验证进行中。
