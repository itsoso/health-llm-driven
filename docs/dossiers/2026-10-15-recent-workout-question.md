# 最近运动口语问句读取修复

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification / G4 review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

裁决: PASS。修复截图“刚才跑的怎么样？”的现有本人运动读取，不增加数据权限、同步或写入。用户要求定位反复失败的根因，并持续授权修复后的部署及 OTA；不备份、不进行真实模型评测。

## 根因与实现

基线 cb3ef7b8e。截图统一提示由 `AgentExecutor._unresolved_read_failure_notice` 的未恢复读取参数错误分支生成；身份不匹配属于独立的终止原因，不能从该提示推断 user ID 缺失。有效且一致的合成认证身份下，截图原句仍无法生成 OwnedReadScope，说明存在独立的语义解析缺陷。

原最近运动解析只覆盖前置“分析/查询”等命令句及正式运动名，漏掉“刚才跑的怎么样”这种带隐含本人、口语动作和后置评价问句的完整表达。模型选择工具后因无法形成明确的受限读取范围而被拒绝。已有回归偏向命令句，没有覆盖这一口语问句族。

新增完整问句语法并复用 RecentWorkoutSelection、OwnedReadScope 和现有 Gateway；同时共享问句与限制检测的动作词汇，避免拒绝变体落入旧查询路径。身份仍来自认证上下文且必须与 envelope 一致；仅查询用户当地当天及所述运动类型。引用、否定、其他人、额外时间限制及复合写入/同步不授予读取。没有匹配记录不补旧记录，不把当天候选认定为刚才的具体事件。

## 验证

- RED：新增六种口语问句均在有效认证身份下失败；十项拒绝反例通过。原始日志 `/tmp/reva-recent-run-red.log`。
- 初轮 GREEN：119 项通过，包含真实 Gateway、数据库读取与保存回复路径，模型传输为隔离合成输入，不是真实模型评测。
- 后续增加账号、模型参数、其他工具、时区及零/多条记录边界。测试提示分支的夹具最初缺少 executor current_user_id，已明确补齐，不据此认定产品身份缺陷；保留原失败记录。
- System Map 验证通过；LLM change gate `live_llm_required=false`。没有 schema、API、客户端契约或原生变更。
- 最终相邻回归 443 passed；独立本地 PostgreSQL 152 passed，测试库停止退出码 0。原始日志 `/tmp/reva-recent-run-related-final.log`、`/tmp/reva-recent-run-pg-final-tests.log`。没有连接真实账号或调用真实模型。
- 独立固定提交 G4、精确主干 CI、部署与 OTA 证据待完成后补充。不得将本地合成验证称为真实用户/手机验收。

## G4 收口

独立审查首候选 863c68424 为 GO；独立152项与19个额外边界探测通过。为避免短动词误匹配“旅游、跑腿、骑马”，新增三个直接负例先 RED，再将短动词限制为同一评价问句词尾，正式运动名的原限制检测不变。最终相邻446项通过，最终固定提交重新审查，不复用旧SHA裁决。先前完整能力/网关5772项通过；最终 PostgreSQL 和发布证据由交付回执单列。

第二次增量审查发现“刚才旅游怎么样？”的词尾仍会触发保守拒绝（没有授权扩张）。补充该负例 RED 后，短动词进一步限制为“刚才/刚刚”的直接动作位置；最终相邻448项通过。所有中间测试/审查证据保留，最终裁决仅绑定最后提交。

## 追加场景：上午跑步（2026-10-15）

用户追加截图“分析上午的跑步”，明确继续解决。G1 PASS：同一本人运动读取链路的时段能力缺口，沿用本 Dossier/trace，新增内部时段选择，不扩大读写权限。

现状：现有 calendar-day adapter 不支持 subday；最近运动闭合语法仅覆盖刚才/刚刚，不能将上午偷偷解释为全天。WorkoutRecord 有带时区的 start_time；ExerciseRecord 无实际开始时间，created_at 不能替代。

实现验收：完整问句绑定认证本人、用户本地日期与运动类型；按实际开始时间筛选半开时段，明确展示时段边界。缺少时间不能归为上午；其他人、旧日期、其他运动、模型覆盖时间范围和额外同步/写入均不得越界。SQL 时区语义必须用独立 PostgreSQL 验证，合成 transport 覆盖真实 executor 与持久化回复，不进行真实模型评测或读取真实健康记录。

发布衔接：上一候选 2fbc264e 的授权准备已完成到 key-retirement，rotate 在只读额度检查退出，未改变线上后端。既有回执已绑定该候选，先按原审核恢复并完成该版本发布，再推进本追加修复的新 SHA；禁止改写旧回执或重放已完成阶段。

当前阶段：实现与 RED/GREEN 验证中；追加场景尚未上线。

### 追加场景实现与验证进展

内部选择器增加时段与相对日期；工具参数契约保持原状，不接受模型自填运动类型或时段。上午为 [00:00,12:00)，下午为 [12:00,18:00)，晚上为 [18:00,次日00:00)，均按账号时区。SQL 按认证用户、运动类型和实际 start_time 半开区间过滤，不用设备业务日期替代；缺失时间的日级运动记录排除并披露。完成消费者逐条核对事件时间、类型、来源和时段元数据。

独立探测发现解析拒绝后通用 fallback 会放大到最近七天，已补限制性检测并先 RED 后修复。广泛回归又发现跨句误绑定“昨晚睡眠…是否适合锻炼”，已限制为时段直接修饰运动对象；保留睡眠查询。有效身份但范围不能解析使用已有 terminal 范围原因，实际身份不匹配仍用身份原因；均不进入自动参数修复重试。续问元数据不允许丢弃时段后恢复全天读取。

- 场景 RED：7 fail / 5 pass；范围回退 RED：5 fail；跨域误判 RED：3 fail；错误原因 RED：3 fail / 1 pass。
- 最终聚焦 221 passed，包含截图执行器单/批量、有/无记录、回复保存、跨账号、注入、午夜/中午与 DST 边界及续问防扩张。
- 首次 PostgreSQL 408 passed（停止测试库退出码 0），最终源追加范围原因及限制语法后重新验证中。
- System Map 和秘密扫描通过；LLM change gate live_llm_required=false；没有真实模型/用户数据调用。
- 本地提交供固定范围 G4 与 CI-mode 验证；远端 main 暂保持 2fbc 以收口已绑定旧发布，不宣称追加场景已部署。

### G4 修复迭代

529f3cf36 独立审查 NO-GO：未知时刻、其他主体修饰及独立早晚别名可绕过限制检测，退回滚动查询。已扩大仅拒绝用途的时间对象识别，同时保留读取/评价语义角色，覆盖前后置动词与逗号拆分；纯运动写入不受新读取守卫影响，睡眠及饮食建议不误绑定为运动时段。新增实际 Gateway enforce/shadow 不派发回归。

529 候选相关 6249 passed，PostgreSQL 415 passed（测试库正常停止）。修订后聚焦 255 passed（日志 /tmp/subday-postfixed-green.log）；最后固定提交将重新接受独立 G4 及相关验证。没有推送被拒绝候选或执行其发布。

### 工具读取面修复

9058907 独立 G4 仍为 NO-GO：“吃饭后的跑步”、后置评价等仍能退回滚动查询。停止通过有限措辞例外修补，恢复最近运动检测的原实现，独立检测时段与运动共现；未生成完整 OwnedReadScope 时，按工具实际读取面阻断 workout、manual_exercise、comprehensive、批量、综合分析及 specialist 等可能读取运动的入口。明确其他领域读取继续接受其原有范围校验；纯写操作不经该新增读取守卫。限制检测不授予任何权限。

新增实际 Gateway enforce/shadow 回归覆盖两轮 G4 反例及各工具读取面，最终聚焦 289 passed（/tmp/subday-architecture-final3.log）。广泛回归、PostgreSQL 与新固定提交 G4 正在重跑；未推送或部署此前 NO-GO 候选。

### 部署后截图回归：生产时间列漂移

f4448dfb完整CI与后端发布成功后，用户15:28再次发送“分析上午的跑步”，范围识别正确但显示查询未完成。只读聚合07:25–07:37 UTC操作元数据（未读聊天正文或健康记录）显示health_query/health_query_batch已调用，goal reason=query_result_unavailable。服务日志同窗口仅提取异常类计数，有ValueError；未输出错误原文或用户载荷。

只读information_schema证实生产workout_records.start_time/end_time为timestamp without time zone，ORM声明timezone=True，数据库默认TimeZone为Asia/Shanghai，无角色/数据库覆盖。subday reader在PostgreSQL拿到naive datetime会抛workout_event_timezone_missing；既有PG测试用ORM新建timestamptz表，未覆盖真实旧DDL。时区格式漂移可解释本次失败，需合成旧DDL复现闭环。历史写入存在startTimeLocal naive和后续GMT aware两种路径，不能未经证实将全部旧值补UTC。

另发现provider漏工具时single-workout不补读，但本次操作元数据证明不是直接原因，暂不混入本修复。当前修复与验收必须保留owner、日期、运动类型和真实时间来源边界，并明确legacy时区解释来源；不读取真实健康记录、不触发设备同步、不调用真实模型。

- 修复采用同一 PostgreSQL SELECT 的显式 timestamptz 转换，查询、排序和返回共用表达式；legacy 行保留数据库解释时区与未核验原设备时区声明。不修改表、历史记录或认证范围。
- RED：隔离 PostgreSQL legacy DDL 3 个用例均复现 workout_event_timezone_missing；GREEN：8 个专项用例通过，414 项相关 PostgreSQL 回归通过（含 executor 与保存回复）；临时实例正常停止。证据 `/tmp/reva-legacy-workout-pg-red-result.json`、`/tmp/reva-legacy-workout-pg-green-result.json`、`/tmp/reva-legacy-workout-related-pg-result.json`。此前 SQLite 测试环境被 PG fixture 拒绝，已改用隔离 PG 完整重跑，不计为通过。
- System Map 检查通过；LLM 变更门判定 live_llm_required=false。固定提交 G4、CI-mode、远端完整 CI 和部署仍待完成；不宣称截图对应真实记录已验证。
- 独立 G4 首审发现 legacy limitation 存在但行同时缺失 provenance 双字段时仍通过；已强制完整字段对并增加 missing_both 反例。新鲜 PostgreSQL 415 项通过（`/tmp/reva-legacy-workout-reviewed-pg.log`），待修正提交重新 G4。

## 追加闭环：运动记录后的恢复建议与详情渲染

上一 legacy timestamp 修复已以 e6aa51fb1768637c90fbca9e41f34bfa7ba07aa5 上线：415 PostgreSQL 测试、本地 CI-mode 3983 项及完整远端 CI 38702515148 通过；后端 38704803587 成功，生产 SUCCEEDED/COMMITTED 与公网健康已回读。未读真实健康记录。

2026-10-15 新截图：产品“问小巴恢复”生成的“基于我刚记录的运动（俯卧撑 · 20次），结合最近恢复、睡眠和心率数据，给我今天剩余时间的恢复建议。”被误判为非本人；运动详情 Markdown 首标题裁切，紧邻表头/分隔符的表格未渲染。

G1 PASS：修复现有按钮到查询/建议与详情展示闭环；沿用本 Dossier，不新增用户读写权。已合成复现有效 owner=41 仍被 health_query_subject_not_current_user 阻断。根因是归属解析把“基于我刚记录”当作未知所有者；历史窗口和建议期限未分离，现有纵向读缺少心率适配，不能仅跳过 subject 校验。新完整作用域须消费整句、绑定本人近7天睡眠和心率，明确当前运动材料不是记录身份凭据；禁止宽分析和写入。

渲染调查：运动详情直接使用 Markdown，未复用 SafeTableMarkdown；标题继承小于字号的行高。拟统一现有安全渲染入口和标题行高，验证窄屏与表格布局。移动纯 JS 变更在原生兼容成立后按同一精确绿色 SHA 先后端、再 OTA validate/publish。

验证、独立 G4、完整 CI 与发布回执待补；不进行真实模型评测、不备份、不读取真实健康记录。

- 移动渲染 RED：真实 screen 组件显示粘连表格原文、h1 32px 继承21px行高；GREEN：21 项聚焦用例与 TypeScript 通过。复用 SafeTableMarkdown，h1–h6 明确行高。日志 `/tmp/reva-workout-render-red.log`、`/tmp/reva-workout-render-green.log`、`/tmp/reva-workout-render-tsc.log`。当前候选未完成原生模拟器视觉验收，不以旧包截图冒充。
- 新按钮将运动材料与授权请求解耦，采用稳定恢复文本；旧截图模板保留闭合兼容。只读取本人睡眠与心率的固定7个本地日期，运动材料不证明事件身份。已有心率查询的通用自然语言日期准入不扩展，仅已绑定作用域使用新的有界读取。
- 新恢复链路 RED 为3项真实PG失败；冻结专项97项通过，PG117项通过并正常停止（新旧模板、有/无数据、回复保存）。新增换行/CRLF的4个真实gateway拒绝用例先RED后GREEN；最终包含它们的PG收口另记回执。预审发现shadow继续dispatch与换行宽工具回落，两处已修；固定提交需独立G4重新裁决。System Map生成并通过，LLM change gate无需真实模型。


### Web 运动分享旧表格渲染修复（2026-10-15）

- 用户补充：分享页把运动分析表格的管道符显示成一段正文。
- 源码链路：Mobile workout-detail 的分享调用 voice-coach 短稿，再经 text share 保存；Web SharedPage 已使用 MarkdownRenderer，但旧短稿中的三列表格已失去行边界，无法由 GFM 直接识别。当前合并的通知修复已在新短稿源头过滤表格；本补丁针对已保存的旧分享提供展示兼容。
- 修改：仅识别有完整分隔行的“指标 / 本次数据 / 评价”旧格式，将完整三单元格恢复成表格行，保留署名和正文；不补造缺失数据。普通管道、代码块及正常表格保持不变，不启用 HTML。
- RED：实际 MarkdownRenderer DOM 测试复现找不到 table；GREEN：分享目录 19 项通过，frontend tsc --noEmit 通过，git diff --check 通过。日志 /tmp/reva-share-render-red.log、/tmp/reva-share-render-all.log、/tmp/reva-share-render-tsc.log。
- 前一候选 74bfb102d 的 CI-mode 已结束：3983 collected、0 failure、23 skipped；本次增量不冒用该 SHA 的发布证据。
- 尚未发布：仍待并行通知发布者交接确认、新候选完整 CI 与部署。该增量只改 Web；此前待发布 Mobile 修复仍需同批适用 OTA。未读取真实分享/健康数据，未做真实模型评测、备份或生产修改；Web 真机视觉验收尚未完成。
