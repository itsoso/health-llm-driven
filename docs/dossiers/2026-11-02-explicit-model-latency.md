# 手动选模首轮一致性与响应延迟

| 字段 | 值 |
| --- | --- |
| 状态 | released_acceptance_partial |
| 当前阶段 | 第五轮已合入 main、部署后端并发布 OTA；App 三秒与设备接收验收仍未完成 |
| 工作流 | quick_fix + safety-gate → backend-deploy |
| 基线 | 5806a685d880cb258f2733fe40cef0a9849cc195 |

## 目标、范围与停止条件

用户选择 DeepSeek V4.1 Flash，但截图首轮为 Qwen3.6 Flash，总耗时约 8.5 秒。
本周优先性能，用户要求响应提升到三秒以内。按真实有效内容衡量，加载动画和空泛
确认语不算结果；首个有效结果与完整回答分别计时。端到端点击到显示仍须单独验证，
不能将模型接口耗时或后台埋点等同手机体验。用户已明确范围为 App 内回复或卡片出现。

首轮修复手动选模首轮被无条件快路由覆盖，以及已验证 DeepSeek 工具能力未登记。
默认自动路由、临床质量下限、权限/同意、工具 Gateway、失败回退、输出审查保持原契约。
不新增缓存、并发、超时或降质输出，不用三秒超时中止正常健康处理。
若权限或质量回归、失败率增加、长尾恶化，停止推广并修复重审；不自动恢复旧生产配置。
本批不是“所有用户请求已在三秒内完成”的交付声明。

## 证据与实现

源码确认 `_request_model_id` 同时承载人工与自动选择。新增独立、每轮重新验证的人工
来源字段，仅在实际 provider 仍为该已授权选模时跳过首轮快路由；不可用模型继续回退。
首轮无工具回答不再先由 Qwen 生成后丢弃，再由所选模型重写。

DeepSeek 通过真实 TokenPlan 接口的 36 项合成协议检查：嵌套写参数、日期范围读取、
当前禁止记录覆盖旧指令、缺少数量追问、问候、工具结果总结，各流式/非流式三次。
脚本 `backend/scripts/smoke_tool_model_contract.py` 不执行工具，不访问真实用户数据；
真实同意检查使用现有 Harness 的临时测试主体。只登记结构化工具能力，不提升强制
tool_choice、thinking budget、显式缓存或临床质量档位。该小样本不证明临床非劣。
此前初探因未建立测试同意主体得到 HTTPException，修正测试前置后才采集能力证据，
不把被同意门拦下的请求算成供应商能力失败。

真实 AgentExecutor 对照为同一组三类合成普通消息，各重复两次。保留全部失败与超时，
未挑最快一次或补样覆盖异常。机器证据见
`docs/reviews/2026-11-02-selected-model-latency.json`。

| 指标 | 修改前 | 修改后 |
| --- | --- | --- |
| 完成的有效回答 | 3/6 | 4/6 |
| 已发起模型调用 | 9 | 6 |
| 成功回答完整耗时 P50（小样本经验值） | 5.84 秒 | 1.27 秒 |
| 成功回答完整耗时 P95/P99（小样本最大值） | 6.2 秒 | 3.46 秒 |
| 成功且三秒内完成 | 0/6 | 3/6 |

修改前另一条出行消息在 Qwen 阶段超出 90 秒测试预算，保留失败。两个句子改写样本
修改前后都被既有业务终态判为失败，不能计为有效回答，不把其较短耗时当性能收益。
修改后故事冷启动仍有 3.46 秒；三秒目标尚未验收。该屏幕未测手机点击/渲染、生产负载
或真实用户历史，不外推生产 P95/P99。未采集真实 token 计费，调用次数下降不等于成本
已按同比下降。基线临时脚本与输出摘要留在机器证据中，执行环境为独立进程/内存 SQLite。

## G3–G6

- 新回归先 RED：4 failed / 1 passed，准确复现首轮被替换及两次串行调用。
- 初版定向 54 passed。最终 CI-mode 合跑 310 passed（58.94 秒），验证管理员权限变化、
  跨轮清理、默认路由、工具门控、临床质量升级与失败回退。内存 SQLite、TZ=Asia/Shanghai；
  不将其称为 PostgreSQL 或生产负载证据。System Map、秘密扫描、diff 检查通过。
- 后续修订的 G4、精确 SHA 真实模型闸、完整 CI、后端和 OTA 结果见下文发布记录。
- 无原生、schema、API 契约变化。共享 dirty checkout 未改动，沿用用户已授权隔离工作区。
- 设备收到 OTA、模拟器真实界面与三秒性能目标均未验证。

## 首轮 NO-GO 与真实 Mobile 入口补全

独立审查对 1c90fe99747f9fd62da1ccd733c6cc8b77357d5a 给出 NO-GO：
实际手机选择器通过 `/me/llm-preference` 保存偏好，未必带 `extra_context.model_id`；
而新增人工来源字段只在单模型路径清理，panel 提前分支可能继承上一轮来源。
该候选未单独作为主干目标推送或发布，随后与整改同批进入 main，唯一发布候选为
70d318d7168534694539dd65990748eb6e7528d7。其 12 invariants、50 health core、5 live orchestrator 真实
Harness 闸虽通过，不能替代修订候选评测。

修订在 `run_stream` 入口、任何 replay/panel 提前分支之前清空人工来源。单模型路径
重新按当前认证用户选择“每消息选模优先，否则本人已保存偏好”；保留 admin join 与
已披露模型限制，不读取其他用户偏好，不把系统全局默认当人工选择。医疗质量下限仍
能覆盖手选或保存的 fast 模型；偏好数据库读取失败向调用方暴露，不伪装成功。

新增回归先复现保存偏好仍走 Qwen、admin/owner 检查及 panel 残留；修订后定向30通过。
补充保存偏好的医疗质量升级组合；最终 CI-mode 集成回归318通过（59.25秒）。

对照补采真实手机请求形状：保存个人 DeepSeek 偏好、消息无 extra_context，固定
故事/出行两类各三次。六次均完成，故事修改前每次 Qwen→DeepSeek 两次，完整耗时
3.53–6.41 秒；修改后每次仅 DeepSeek，1.36、1.5、3.31 秒。
出行两边均走既有确定性本地回复（约6–7毫秒），不归因为本次提速。
故事小样本 P50 从5.96到1.5秒，P95/P99经验最大值从6.41到3.31秒；仍未达全量三秒。
机器证据中的 saved_preference_followup 保留全部样本与来源摘要，非生产或手机验收。

## 请求计时边界补测

前两组计时包含合成账户初始化。补测将起点移至合成 owner/profile/consent 已建立、
调用 `run_stream` 之前，终点包含输出审查和 done 事件；不含 HTTP 与手机渲染。
同一故事、出行场景各三次，基线和最终候选均六次完成，所有样本保留在机器证据
`request_boundary_followup` 中，原批次未被覆盖。

故事基线完整耗时 12.92、4.37、4.13 秒，每次 Qwen→DeepSeek 两次调用；最终候选
4.16、1.16、1.31 秒，每次仅 DeepSeek。冷启动样本仍超过三秒，其中模型调用约
3.53 秒。出行回复两边均为既有本地路径，约 3–4 毫秒，不计为本次收益。
内部 first_useful/end_to_end_ttft 可能包含尚未释放的缓冲内容，此处采用外部观察到
的首个 token 计时；它仍不是手机点击到展示耗时。三次重复不能证明生产 P95/P99。
原始计时证明摘要：`bb3b9b21987752dfd00c7e4d3238781c4be0629a13d6257f7cc2157a8bfbef21`。

## 最终候选验证与发布记录

唯一发布候选：`70d318d7168534694539dd65990748eb6e7528d7`。

- G4：独立 reviewer 对固定 SHA 给出 GO，独立 266 项通过（56.87 秒），记录在本次
  审查线程；未生成单独代码报告，不以运维 stage/rotation 批准代替代码审查。
- G3：最终本地集成 318 项通过；精确 SHA 真实 Harness：12 invariants、50 health core、
  5 live orchestrator 全通过，trajectory contract 12、goldens 9 通过。
  5 个 live orchestrator 用例平均耗时约 7.59 秒，这也是不能声称所有场景三秒完成的证据。
  Harness 结果文件摘要 `06675e7e95c4ab82ff94a6762822c3e9c891bfbc78ad29838304336caa2a724e`。
- 精确 main 完整 [CI 41374864498](https://github.com/itsoso/health-llm-driven/actions/runs/41374864498)：32/32 成功。
- G5：后端 [validate 41376237799](https://github.com/itsoso/health-llm-driven/actions/runs/41376237799) 与
  [deploy 41378345363](https://github.com/itsoso/health-llm-driven/actions/runs/41378345363) 成功。
  OTA [validate 41377711126](https://github.com/itsoso/health-llm-driven/actions/runs/41377711126) 后执行
  [publish 41378948456](https://github.com/itsoso/health-llm-driven/actions/runs/41378948456)，均成功。
  仅发布一次；最初 validate CLI 在查询工作流元数据时 TLS 超时，确认无 run 后才提交实际 dispatch，
  不涉及重复 publication claim。后端状态读取超时也未触发重复部署。
- 无备份、旧配置恢复、恢复演练；保留原始锁、授权、回执和审计。独立批准的 stage、
  短期只读凭证刷新及授权轮换后才部署。临时精确 SHA Harness 确认变量已删除并回读为空。

## 发布回读与未完成验收

后端只读回读通过：干净生产 HEAD 为候选 SHA，授权与实际执行器摘要一致，原始完成
回执 SUCCEEDED，无占用业务租约，health-backend、celery-worker、celery-beat、reva-laya
四服务 active/running，内外网健康检查 healthy。独立 reviewer 已复核证据。

| 证据 | 值 |
| --- | --- |
| 后端 completed 原始摘要 | `0c44be3a7f9f0911f0ccf564c38de0f07a28ea90b1998fcdf3c7d50eed903b63` |
| OTA completed 原始摘要 | `4465d55f7beb58fcbccea8cbc0129c19e7b171c02acdbcece8fb2027e207dfb9` |
| OTA verified 原始摘要 | `4a7897fa5bf233f2aa17887973d4d18220ee24919db8900f30b4c75d96b2e62d` |
| OTA group | `f0aa4e3e-e1b7-4839-b6ef-9142f334a77a` |
| OTA update | `01a19a27-20ed-7693-bb4b-fcf04bc5ac52` |
| iOS runtime / channel | `1.3.6` / `production` |
| 公开 manifest launch hash | `4viQ983bfb4Yl60ajYrTwOlfX6kWXIwOlyYOjIny9cE` |

公开 Expo manifest 的更新 ID、runtime、启动资源和 47 个资源的摘要与发布制品一致；
未另行下载全部资源字节，未宣称手机已获取或应用更新。本批没有 Mobile 运行时代码变化，
按用户持续授权发布同一移动端代码树；响应提速发生在后端。

三秒目标仍未完成：冷启动样本 4.16 秒、5 个 live orchestrator 用例平均约 7.59 秒，手机端端到端和
生产负载下的长尾未测。不得把这次发布写成性能全面验收通过。后续应先补网络连接、
供应商等待、生成与实际输出释放的分段证据，再选择下一项优化；不得靠空泛确认、
超时截断健康处理或降低安全/质量约束达标。

## 锁屏期间的第二轮性能优化（未发布）

用户要求锁屏继续工作，使用后台工具、合成账户和既有脱敏计时，无需解锁。没有通过其他
GUI 通道绕过锁屏。手机点击到实际显示仍未验证。生产只读观察保持在已发布的
`70d318d7168534694539dd65990748eb6e7528d7`；新代码基于主干
`fd28f9a2e0eb00549b2dc5559ea6a7f8ede71188`，不改共享 dirty checkout。

实际脱敏日志中另有 Qwen3.8 Max 查询约39–46秒，包含一次约5秒可选路由超时。
这与“人工选 DeepSeek 却先用 Qwen”的已修问题不同：这些记录的 selected_model 与
answer_model 都是 Qwen3.8 Max，不能据此推断特定手机当前选择。聚合布局事件没有按
turn 配对，摄取时间窗口也未绑定发布版本，不能将差值解释为真实渲染开销。

本轮改动：

- 为 Qwen3.8 Max 及同端点别名单独登记关闭思考能力；只作用于原来已判定为简单问题的
  无工具回答轮。真实接口18/18合成协议校验通过，数值集合、非空、完成状态、无工具调用
  均检查并保留合成回答；不开放 thinking_budget，不改临床质量地板或工具决策思考。
  新复核样本关闭思考0.8–1.32秒，默认2.27–5.33秒，只证明模型接口能力。
- 完整 Agent 对照发现查询完成后仍带工具，单改思考标志无法消除主要等待。
  对当前已支持、完整匹配的本人“查询/查看今天、昨天、前天睡眠记录/数据”，复用
  owner/date scope 生成 Pi proposal；ToolGateway 仍逐次授权并真正读取。新会话省去
  模型规划，已完成且核验通过的结果复用 trusted_fact_summary，省去模型转述。
  明确事实查询也无需可选 Laya 路由；确定性高风险分类或分类失败仍保留原路由和质量地板。
- 仅限上述范围，建议、分析、混合操作、其他主体、否定、附件、历史引用、待确认、同步、
  读失败、截断或日期不符不能走成功快捷终态。历史对话继续经过模型规划和转述，保留先前更正。
  输出仍经过原医疗/质量审查、Pi 终态、持久化；事实投影如实标识工具结果，不冒称模型推断。

对照固定同一合成睡眠记录、保存的 Qwen3.8 Max 偏好、相同 App 卡片 capability、
两边都开启生产已有的 domain_prompt_optimization。每边三次，冷启动与全部失败保留。

| 指标 | 基线 | 当前候选 |
| --- | --- | --- |
| 完成 | 3/3 | 3/3 |
| 首个实际向调用方释放的有效文本 | 25.17、32.54、21.88秒 | 0.67、0.31、0.29秒 |
| 完整结束 | 25.29、32.57、21.91秒 | 0.75、0.34、0.32秒 |
| 每次模型调用 | 2 | 0 |

此为内存 SQLite 合成 owner 的真实 AgentExecutor，基线调用真实供应商，候选使用实际
Gateway/数据库读取和事实渲染。两边可选决策均关闭，因此路由跳过收益未计入表格；
路由 on 的行为由独立回归验证。没有 HTTP、生产负载或手机绘制，三次最大值不能代表
生产 P95/P99。零模型调用只说明本路径免去生成成本，未测整个服务计费。

早期对照未开启 domain_prompt_optimization、未带卡片能力，另有“只列出数据”的范围
解析失败以及饮水请求达到三次模型调用预算失败，均保留在原证据中，不混为成功收益。
本轮不宣称饮水、识图、复杂分析或历史会话均已三秒内完成。触发质量/授权退化、失败率
增加或长尾恶化即停止推广，不降低审核闸、不重发未知发布、不恢复旧配置。

机器证据续写到 `docs/reviews/2026-11-02-selected-model-latency.json` 的
`locked_screen_performance_followup`；原始本地报告保留摘要与配置限制。

第二轮本地验证：新睡眠路径先 RED 20 failed；补实现及来源标识后27项边界通过。
集成覆盖原 Pi 多轮轨迹、预规划、查询可靠性、失败终态、选模/回退/工具门控、决策路由
和思考控制，501 passed（113.66秒），6条既有依赖弃用警告。新脚本与新测试的 Ruff
检查通过，System Map、导航和漂移检查通过。此时尚未提交候选、独立 G4、精确 SHA
live Harness、完整 CI、第二轮部署及 OTA，不能复用首轮发布回执当本轮完成。


第二轮 G4 首次 NO-GO：`474423b026daf78b6f410d95fca1a1d322dd94b9` 的事实免转述
未排除历史会话，独立 Pi/Gateway 对照复现先前用户否认设备记录却被最终答复遗漏。
该候选未单独推送或发布，整改后同批进入主干。整改把规划、转述和可选路由跳过都限制为新会话；免转述另外要求初始
对话只有当前用户消息。新回归先 RED，再断言历史更正同时存在于保存文本和实际释放
文本。定向87项通过，完整501项重新通过（113.87秒）；此前该候选 live Harness 成功只记为历史
证据，不能代替修订候选。另一项前端发布占锁期间没有推送或操作生产，锁闭合后再核验。


## 第二轮精确候选验证与发布证据

候选 `ddb7b7796e450105acdcdf755f74fc4a3c25b735` 已合入 main；独立 G4 GO，
reviewer 重新执行271项测试通过，并复现真实 Pi/Gateway 历史更正路径仍保留两次模型调用。
本地最终集成501项通过，未把历史 NO-GO 候选的评测复用为本候选。

精确候选 live Harness：12 invariants、50 health core、5 live orchestrator、12 trajectory、
9 goldens 通过；live orchestrator 平均8.71秒，因此不能宣称所有回复已三秒内。
完整 CI [41388549068](https://github.com/itsoso/health-llm-driven/actions/runs/41388549068)
32/32通过；release validate
[41389579925](https://github.com/itsoso/health-llm-driven/actions/runs/41389579925)成功。

最终同一合成查询再次测量3/3完成，首个有效文本0.87、0.36、0.29秒，完整结束0.94、0.38、
0.32秒，均无模型调用。仅证明新会话单日睡眠事实查询在该内存SQLite测试环境的收益；
不覆盖HTTP、生产负载、真实用户历史、识图或native显示时间。Mac锁屏未作为后台验证的阻断，
真实native显示仍未验证。

后端 [41391562479](https://github.com/itsoso/health-llm-driven/actions/runs/41391562479)
发布成功，独立回读生产 HEAD 为该候选且工作树干净，health-backend、Celery worker/beat、
reva-laya 均 active/running，内外网 health 正常，发布锁已释放。
后端完成回执 SHA256：`e2f2ca6a5bf93f933f5630eb9b233e8c208965bcdf9b7c987a6ef01c846c843d`。

按用户本会话明确要求继续发布 OTA。本次 Mobile/shared 运行树与上一 OTA 相同，提速来自后端，
不把重复 bundle 算作新的 Mobile 性能收益。
OTA [validate 41392147077](https://github.com/itsoso/health-llm-driven/actions/runs/41392147077)
及 [publish 41392335561](https://github.com/itsoso/health-llm-driven/actions/runs/41392335561)
成功；group `334737e2-ea06-4e35-bf7c-3915cbeef94f`、
update `01a19ab0-635a-7616-a9a4-e1d5cf360652`，production/iOS runtime `1.3.6`。
独立公开 manifest 核对 launch `4viQ983bfb4Yl60ajYrTwOlfX6kWXIwOlyYOjIny9cE` 与47项资源
摘要一致；未声称逐字节下载全部资源、设备已接收或native显示达标。
OTA 完成回执 SHA256：`0945ba3ec1f18afc76645c82e46ddd43926493a79ebcd5ff0b7b3e21e7ad3392`。

本轮部署前的只读凭据刷新、unused fd28授权关闭及canonical轮换分别经独立G4，
按原intent单次完成，无备份、回退副本或未知操作重发。生产旧后端70d与旧授权fd28身份独立核对。
临时 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 已确认仍绑定本候选后删除并核验不存在。
完整机器证据位于 `locked_screen_performance_followup.final_candidate_release`。
本轮G5完成、G6自动线上检查通过；所有请求三秒内、真实App显示及设备接收仍未验收。


## 第三轮：其他常见 prompts 基线、范围与发布

基线为 `1e79e3ded7dfac4774b112fa1c1c9ebacba62c2c`，两种保存偏好模型各6类合成请求，
真实Agent/Pi/Gateway、内存SQLite、decision_mode=off，每样本最多3次模型调用和90秒。
保留12个样本，其中两条饮食评价终态blocked，不算性能成功。单次初筛不能估计生产P95/P99。
问候Qwen首个有效文本11.64秒，携9298字符及11工具；DeepSeek为1.44秒。
单日饮食查询Qwen16.84秒、DeepSeek6.77秒，都有两次串行模型调用。
周睡眠查询分别4.65和2.92秒出现首个内容，完整结束16.88和5.74秒。
普通改写和故事DeepSeek已约1.4–1.7秒，Qwen约6.2–6.43秒，本轮不先扩大这类自由文本的范围。

本轮只优化新会话的完整匹配问候、自我介绍和单日饮食事实查询。初版缩短提示词仍出现
Qwen 问候冷样本6.528秒、饮食查询3.289秒，首版饮食回答还出现无证据漏记判断，均不推广。
周睡眠预规划因现有日期绑定不满足精确范围被移除；不扩大读授权。

最终候选让问候/能力介绍直接经过 Pi 和最终输出/保存闸；单日饮食仍由 Pi/Gateway 执行
原属主/日期授权查询，仅对完整核验的结果逐条呈现。重复记录不合并，缺失字段标未知，
数值复用统一展示精度，记录文本按数据转义。旧会话更正、待确认、混合/医疗请求、附件、
读取失败和范围不符仍走原流程；需要模型的请求仍尊重用户选择。

固定3类请求×2模型保存偏好×3次，基线18次与最终18次均完整结束。最终首个有效内容
219–1471毫秒、18/18低于3秒、0次模型调用；最长样本含进程首次准备。
这里的偏好模型用于验证选择不影响确定性展示，不是两种模型生成速度的比较。
完整合成账号Agent链路和工具读取，真实供应商基线；候选无需供应商请求。
SQLite只用于无数据库语义变化的性能采样，不能代替发布PostgreSQL集成闸。
样本P50/P95/P99和全量失败/候选样本见同一机器证据；样本量不支持生产长尾承诺。

TDD新行为5项先失败，随后通过；扩大回归503项通过、属主/日期补充3项通过、地图再生成并校验通过。独立安全审查3fbb3e8d为GO，172项及完整链路恶意记录文本探针通过；真实模型Harness全通过。随后两处import排版、测试契约和证据收尾，经最终741feaf11窄审GO及精确模型闸后发布；
App屏幕可见延迟仍未验证。三秒目标不计占位或失败终态，复杂分析不算已达标。
质量下降、漏字段、错误率或长尾恶化即停止推广并修复，不自动恢复旧配置。

CI `41411702376` 的 `backend-test-balanced-13` 发现旧测试强制精确单日饮食查询调用模型。
没有发布该失败候选。修订测试契约：精确单日必须完整核验/预规划/无写回执，跨日和分析仍
必须调用模型；生产代码不变。相关97项通过；最终741feaf11重新通过完整CI和精确live闸。

### 第三轮发布与验收

最终运行候选 `741feaf11a3d2e08d2dafa765e8c3039d1572329`：

- CI [41412927951](https://github.com/itsoso/health-llm-driven/actions/runs/41412927951)：32/32通过，含PostgreSQL；真实模型Harness全部通过。
- validate [41414311748](https://github.com/itsoso/health-llm-driven/actions/runs/41414311748)，后端 [41417330281](https://github.com/itsoso/health-llm-driven/actions/runs/41417330281) 均成功。生产clean SHA匹配，4个服务运行、内外健康接口正常，业务租约已释放。
- OTA [validate 41418326357](https://github.com/itsoso/health-llm-driven/actions/runs/41418326357) 后 [publish 41418760453](https://github.com/itsoso/health-llm-driven/actions/runs/41418760453) 成功。group `46c03706-0d29-4d01-8b94-36862aaa5f3e`，update `01a19b8e-811d-799e-a76b-178600758324`，runtime `1.3.6`。独立公开manifest检查通过，47项资源摘要全部匹配，launch `4viQ983bfb4Yl60ajYrTwOlfX6kWXIwOlyYOjIny9cE`。

本轮 `mobile/` 与 `packages/shared/` 树相对上一已发布ddb未变；按本对话明确的“发布和OTA”请求完成同候选OTA，性能改动来自后端，不声称有新的移动端运行逻辑或原生能力。
发布准备保留stage/只读凭据刷新/成功工作区轮换的独立GO与实际回执，不执行备份或恢复演练。
轮换草稿曾因两处旧审计短名被NO-GO，在任何执行前修正并重新GO；没有重放生产操作。
临时精确SHA live评测变量仅在值仍属于本轮时删除，已复查不存在。

G5发布完成，G6自动线上验收PASS。合成样本的三秒结果仅限新会话完整匹配问候、能力介绍和单日饮食查询；历史/分析等请求仍保留正常模型路径。
App屏幕出现耗时、设备实际接收OTA和生产请求长尾尚未验证，不因锁屏而绕过UI限制，也不宣称所有请求达到三秒。


## 第四轮：常见请求都测，优先最慢路径

用户补充优先级为“常见请求都测，优先最慢的”。基线为当前主干
`0ddf52a348feb5078e15b3333911907486cec7b2`，沿用已有隔离工作树，不修改原始脏工作树。
16类请求×2种已保存模型偏好，32个真实供应商/Agent/Pi/Gateway合成样本；
仅限读工具白名单、每样本3次模型调用/90秒，所有停止、blocked、失败保留。
本轮机器证据见 `docs/reviews/2026-11-02-common-prompt-latency.json`。

首轮只声明sleep-summary能力，属于受限卡片能力的后端筛查，不能冒充App显示耗时。
正文慢项包括睡眠分析（Qwen约66.94秒、DeepSeek约9.35秒）、联合分析
（约44.61秒/9.89秒）。饮水/部分查询触及测试工具或调用预算，属于未完成测量，
不等价于生产失败。complete只是运行状态；饮食多日漏述与无依据睡眠判断另记质量FAIL。
多日查询、饮水、绘图、饮食评价、写入及硬件路径并未因此宣称已修复或达标。

优先候选仅针对新会话完整匹配“分析我最近1–31天的睡眠记录”：
使用已有属主/日期绑定器生成查询提案，仍交Pi/Gateway授权执行；不改授权语法。
读取完成后复用已有完整核验证据的紧凑分析输入，保留档案约束和未知字段，
不再携带工具让模型重复规划；所选模型负责解读，临床质量底线不降级。
历史、附件、待确认、失败、同步、临床与混合目标维持原路径。
单域分析同步经过既有多域证据护栏，拒绝从记录推出恢复良好、无异常等断言。
已有确定性数据表可在模型前发出；修正卡片与正文之间换行被流式出口剥掉的问题，
保持实时与保存正文一致。无移动端/数据库/依赖改动。

TDD：紧凑回答2项先红、无依据健康判断1项先红、预规划1项先红；
额外真实Pi链路验证数据表在模型调用前出现、属主/日期隔离、空数据、读取失败、
旧会话更正与消息保存一致性。当前局部78项通过；前一候选1322项通过，
最终候选扩大回归及与App相同能力声明的配对测量尚在执行。

停止条件保持不变：质量退化、失败率增加或长尾恶化即不推广；
加载提示、失败终态、回答依据事件不能替代有效内容。锁屏不绕过，
原生绘制、HTTP入口/真实负载和设备OTA接收仍须单列未验证。
当前仅本地候选，未提交发布；后续需独立安全GO、精确SHA集成/CI、后端及OTA回执。


### 第四轮独立审查阻断与修复候选

71357e2b9 的最终相关回归1302项通过，但独立G4仍NO-GO：结果自身日期一致、
却与已授权日期不同时，最终状态failed之前已提前输出错误日期卡片。
审查证据随本轮JSON保留；不能以测试绿或首卡快替代安全GO。
后续候选在共享早期/最终卡片投影前复用既有bound-result校验，拒绝窗口不符、
截断、失败、错误维度和无日期绑定结果。批量读取保留独立有效子项；
整批截断不改称完整。日期窗口结果只能走窗口内记录投影，禁止夹带旧daily_data摘要。

真实有界每日饮食读取返回calendar envelope；原diet卡片e2e将明确今日请求
与旧无窗口DailyDietSummary混用，现将旧shape测试放回无日期请求，
另补有日期请求不能接受旧摘要的反例，未放宽生产日期校验。
新卡片故障测试先6红、批量截断先3红；修复后相关149项通过。
真实Pi/Gateway移植独立错窗探针，实时与持久化均不得出现错误日期卡片。

App七项能力配对样本：基线3complete/1blocked/2测试工具边界停止；
713候选4complete/2blocked，6次首卡290–995ms。
随后DeepSeek诊断3次complete，不抹去前述blocked；质量与成功率尚未验收。
最终分析仍数秒至数十秒，不能声称完整回答三秒达标。
当前修改仍未push、部署或OTA；须修复候选独立重审和新鲜验证。


ccfc51391 修复错窗后，独立复审发现batch根pending/processing/unknown/无status
仍可提升有效子项为完成卡片；第二次NO-GO随JSON保留。
最终修复与既有completion的batch终态完全一致，再核验各子项；
6种终态反例先红，真实success根的有效子项和截断反例独立覆盖。
ccfc实现的扩大回归1337项通过、真实模型Harness闸通过；终态补丁须另跑新鲜闸。

ccfc App能力复测6/6完成，首卡302–1106ms，全部仅所选模型1次调用。
Qwen完整分析16.50–34.71秒；DeepSeek3.14–5.93秒。
机器证据保留全部基线、候选与诊断样本及经验P50/P95/P99，三样本百分位
只表示观测排序，不证明生产长尾或三秒SLA。之前的2次blocked仍保留。
个别回答经既有过滤后留下“这两件事”的不连贯指代，独立审查列为非阻断质量待办，
不以状态complete宣称全部语义通过。本轮只验收提前展示正确范围的有效数据卡片
和省去一次规划调用；完整分析、HTTP/原生绘制及生产成功率目标仍未验收。

终态补丁最新CI-mode相关集成回归223项通过（29.69秒）；
血氧batch测试补上真实adapter的status=success，与缺失终态反例分开。
新测试Ruff、秘密扫描和diff检查通过，待最终精确提交G4/真实模型闸及完整CI。


### 第四轮主干CI阻断

00565857已合入main；CI41435127442的balanced-11因新增三个测试函数未加入
composed-synthesis显式分片目录而失败。不是业务测试失败，也未部署该红色SHA。
将三个函数加入既有第四分片，保留全部旧用例、超时、单次运行、估时及调度策略；
不删除分片覆盖检查、不重跑旧失败记录制造绿灯。修订候选须重新获得完整CI。

分片检查及新增场景27项通过；对应固定目录摘要随新增用例更新，
CI发布/计时契约68项通过。没有改变执行预算或调度估时，历史计时不冒充新增场景计时。

### 第四轮 CI 通过与饮水补测

10de8b8452de68174b7a332750308e4df2413c29 已取得独立G4 GO、真实模型Harness通过，
完整CI41436787538成功；尚未部署。等待CI时继续测饮水，发现旧health_query water
忽略days、只返回今天，最近7天样本却把已存在的其余6天记录说成缺失。
保留全部基线/候选结果，complete不能作为语义通过；停止本轮发布直到修复。

新修复只绑定当前完整“查询/查看 + 日期 + 饮水记录/数据”请求，
经既有Pi/Gateway校验owner、日期、时区后执行有界WaterIntake读取，
复用结果校验和表格投影。无绑定不能继续偷偷用今天代替；明确要求日期。
事实输出由已验证记录合计与逐日值生成，未记录不代表没有喝水，
不推断补水充足或设定饮水目标。已有会话和关闭优化开关也保留事实边界。
普通输出本已统一缓冲至最终验证；未复用临床sealed标记阻断合法读取。
无写入、schema或移动端更改。PostgreSQL CI加入同一真实Pi/属主/窗口测试文件。

首轮18项测试10红，修复后18通过；扩大相关304项中303通过，旧测试要求
无当前请求的water读取自动回退今日HTTP，与本次日期修复冲突。
将其改为验证明确拒绝且不发HTTP，并补关闭进程内开关的合法有界请求正例。
真实App能力饮水复测4/4完成，首条有效内容248–455ms，全程279–714ms；
7天合计4550ml与逐日500–800ml均匹配合成种子，均零模型调用。
这只证明本地SQLite链路；不冒充手机显示、HTTP入口或生产三秒SLA。

23f2fa5e4扩大CI-mode回归3812项通过，固定SHA补跑106项及真实模型Harness通过；
独立G4仍阻断：water闭合语法的strip把四空格/Tab缩进代码材料提升为读取授权，
真实Pi探针复现合计910ml泄露到回答。该SHA未push或部署。
修复改为对原文fullmatch，不先移除材料边界；两个授权反例先红，
加真实Pi模型提议也不能触发calendar read的反例，共31项通过。
后续必须以新提交重新取得独立GO与完整CI/发布证据，旧通过不替代新候选。


### 第四轮发布收尾（最新状态）

候选 `cb6b698d033c5aa1fe8edcca13a4f720899b66c4` 已合入 main 并完成后端与 iOS OTA。
以上“未提交/未发布”是过程状态，不能覆盖本节的精确版本证据；原 NO-GO 和失败样本仍保留。
本轮筛查覆盖16类常见请求的两模型样本，优先优化慢睡眠分析；饮水补测发现日期正确性问题后
先修复再发布，没有将错误答案、预算停止或加载提示计为性能成功。

- G4：cb6独立GO；原23f缩进材料读取漏洞NO-GO保留，新原文匹配与真实Pi反例通过。
  固定候选CI-mode3676项、独立水域/卡片48项及原漏洞探针通过；真实模型Harness exit0。
- G5：[完整CI41441749609](https://github.com/itsoso/health-llm-driven/actions/runs/41441749609)
  首次32/32成功；PostgreSQL两分片exit0，JUnit确认新增31个water测试全部执行通过、无skip。
  [发布预检41442976831](https://github.com/itsoso/health-llm-driven/actions/runs/41442976831)通过。
  canonical staging、固定只读凭据刷新、授权轮换均单次成功，保留原锁/回执/审计，没有备份或恢复演练。
- [后端41446168567](https://github.com/itsoso/health-llm-driven/actions/runs/41446168567)成功；
  独立回读生产精确SHA、干净工作树、对应SUCCEEDED回执、授权与无业务租约。
  health-backend、celery-worker、celery-beat、reva-laya均active/running，内外health均healthy；
  实际进程DOMAIN_PROMPT_OPTIMIZATION=true。
- [OTA validate41447062231](https://github.com/itsoso/health-llm-driven/actions/runs/41447062231)
  后单次[publish41447774658](https://github.com/itsoso/health-llm-driven/actions/runs/41447774658)成功。
  服务端完成回执与公开manifest独立一致：group `07ffecb2-9798-4083-9031-83a77a6dd6f6`，
  update `01a19c54-fe9c-70aa-bf79-646bbb9f36d0`，production/iOS/runtime1.3.6，47资源及启动包摘要匹配。

后端部署后以同一干净SHA重新跑饮水合成样本：4/4正确完成、零模型调用，首条有效内容233–2291ms，
全程260–2586ms。首样本明显慢于其余233–248ms，不删除、不挑快样本，也不从四次数据推导生产长尾。
7日4550ml及每天500–800ml与日期逐项核对；这仍是本地SQLite/Pi链路，非线上个人请求或手机绘制。
先前睡眠App能力样本首卡302–1106ms，完整分析仍可超过三秒，质量待办继续保留。

G6仅线上发布证据通过；真实用户请求分布、HTTP发送至接收、原生绘制、模拟器交互和设备OTA接收
均未验证。Mac锁屏时继续无界面检查，没有要求手机/电脑解锁；本批不宣称全面达到三秒SLA。
机器证据、全部前后样本、审查裁决和公开清单摘要已写入
`docs/reviews/2026-11-02-common-prompt-latency.json`。后续文档提交只收尾证据，不重部署同一运行时代码。


## 第五轮：周饮食与睡眠记录查询（过程记录，发布结果见下）

基线主干 `dd69f76f19696a86f34b2c9789a6c0a949fde49b`。用户要求继续优化其他链路；
沿用已授权隔离工作区、发布与 OTA。常见场景补测 6 类 × 两种保存模型偏好，使用真实
Pi/Gateway 与供应商、合成账号和临时 SQLite，App 当前七项能力。全部样本及停止项保留在
`docs/reviews/2026-11-02-range-record-latency.json`，不测生产个人数据，不冒充手机验收。

补测发现“查询我最近7天的饮食记录”没有绑定范围，旧 `days=7` 路径仅返回今天；模型
错误声称前六天没有记录。周睡眠也出现 scope 缺失与工具循环。优先修复这两条正确性与
延迟链路；饮食评价、综合分析、趋势图的失败/慢样本保留，尚未声称修复。

本轮仅增加完整、无附加条件的本周/上周/最近1–31天饮食/睡眠记录查询。复用现有
服务端业务时区日期绑定、owner 限制、Pi/Gateway、calendar adapter、记录/字符上限及
结果校验。不改 schema、模型或临床质量档位。新对话直接提出已绑定查询，经核验后逐日
展示事实；历史对话保留模型规划与纠正。饮食逐条保留同名记录，睡眠按醒来日期显示
时长/评分/分期与未知字段，无健康评级或恢复结论。无数据、异常、截断、错误窗口均
保持显式状态。原始文本全句匹配，不剥掉缩进代码材料边界。

新行为先 RED：修正测试夹具重复 source 唯一键后，12 failed / 18 passed；失败复现
缺少范围、仍调用模型和未读取却完成。后续测试/独立审查/精确 SHA CI/发布待完成。


第五轮本地 CI-mode：范围查询、逐条渲染、既有快查、饮水、scope、权限、对抗输入与
完成状态合跑 2629 passed（53.58 秒）；前序扩展回归 398 passed（45.66 秒）。
PostgreSQL runner 契约 39 passed / 3 skipped（本地未运行 PG），真实 PG 留给精确 SHA CI。
System Map、diff、定向 Ruff 通过。最初夹具冲突、旧单日 renderer 限制断言与 flag-off
事实摘要缺失的失败均保留；分别修正夹具、扩展有效范围契约、补上普通/Panel 范围事实摘要，
没有移除历史纠正或放宽失败门。独立审查、真实模型复测与发布仍待完成。


第五轮候选 `302347fd01564912f11325c81b65eeefa85b5f92` 独立 G4 GO：173 项定向测试、
单模型/Panel 四场景及 30 个日期/时区/授权探针通过。真实 Harness 闸 exit 0（70.69 秒）。
两类周查询 × 两种保存偏好 × 两次共 8 次均完成，0 模型调用，首条有效内容 220–584ms、
完整 249–687ms；逐日日期和记录核对通过。此结果仍为临时 SQLite/真实 Pi，本轮优化后
没有发起模型调用，不含 HTTP 或原生渲染，不能外推生产百分位。

该候选已推主干，但完整 CI `41455673857` 阻断，未 staging/部署/OTA：旧预算测试仍
要求周查询调用模型；新 `test_range_record_lookup.py` 漏在手动 r-other 文件分配之外。
修订仅同步预期行为、添加该文件并更新全量策略摘要。保留旧 r-other deadline 校准原始
选择摘要，不把新增测试冒充历史计时；超时、重试、分片数量和已有测试均不变。
本地修订验证 178 passed / 3 skipped（15.96 秒）。旧失败 CI 保留，新 SHA 重新完整验证。


### 第五轮发布收尾（最新状态）

本轮最终候选 `3f5e768ea48ce71232a3e43579e11a355752b370` 已合入 main、部署后端并发布 OTA。
以上待验证、未发布状态均为过程记录；失败 CI 与 NO-GO 保留，不替代最终版本证据。
运行代码与独立审查的 `302347fd0` 一致，最终窄审 G4 GO；完整过程与可复现测量脚本快照见
`docs/reviews/2026-11-02-range-record-latency.json` 的 `release_evidence`。

- [完整 CI 41457300197](https://github.com/itsoso/health-llm-driven/actions/runs/41457300197) 第一次运行 32/32 成功，真实 PostgreSQL 两分片通过，新增范围查询 44 项全部通过、无跳过。
- 最终精确 SHA 真实模型 Harness 闸通过（64.31 秒）；最终八次查询均完整返回七天记录、0 模型调用，首条有效内容 **237–711ms**，完整 **267–825ms**。这是合成账号、临时 SQLite、真实 Pi/Gateway 的进程内测量，不含 HTTP、原生绘制或生产长尾。
- [发布预检 41459191517](https://github.com/itsoso/health-llm-driven/actions/runs/41459191517) 与 [后端发布 41463012474](https://github.com/itsoso/health-llm-driven/actions/runs/41463012474) 成功。独立回读确认生产 HEAD 为最终候选、工作树干净、授权一致、服务运行、内外 health 正常、发布锁已释放；实际运行进程 `DOMAIN_PROMPT_OPTIMIZATION=true`。
- [OTA validate 41464329385](https://github.com/itsoso/health-llm-driven/actions/runs/41464329385) 与 [OTA publish 41464644742](https://github.com/itsoso/health-llm-driven/actions/runs/41464644742) 成功。发布只执行一次；服务器回执与公开 Expo manifest 独立核验通过，production/iOS/runtime `1.3.6`，group `42660e1b-1a7d-404b-898d-e0b528041e49`，update `01a19cbd-e13d-7406-aaa6-9626afac834c`，47 个资源与制品匹配。

后端 completed 回执 SHA256 为 `cf0b5218f47c0c75e4276ae923570719fcc39ac6159317a6c94cc76062230485`；
OTA completed 为 `f28a2177383228c79a8f3b1396dd245bcec8408596c17029513b2e9750a8c0f3`；
OTA verified 为 `100eb7ac5313586147a6eae0f811698ee91063fedd5eaa4ac52512065062ed5a`。
准备阶段的 staging、只读凭据刷新、工作区授权轮换均保留独立 GO 和一次执行回执；没有备份、恢复演练或重发。
本轮性能改动来自后端，Mobile/shared 运行代码未改；按用户持续明确授权发布同候选 OTA。

G5 发布完成、G6 自动线上发布核验通过。App 点击至实际显示、模拟器交互、设备 OTA 接收、
生产 P95/P99 仍未验证，不能宣称所有请求已达三秒。提速仅覆盖新会话完整匹配的周/日期范围事实查询，
历史纠正、分析与临床判断仍保留模型路径。基线中的饮食评价、综合分析和睡眠趋势图问题尚未修复，继续保留待办。


## 第六轮：整体链路减少等待与有效结果计时

用户授权按整体规划执行，基于最新主干 `3c438e8362e3ce3dc11e845b80d22c98a506be0b`，新隔离工作区保留其他并行改动。
沿用本 Dossier / Health Harness run `ff67fa8caa7a`，需求与边界见 [性能规格](../specs/2026-11-03-agent-pipeline-performance.md)。

- 完整绑定的事实查询，在已有对话也跳过可选路由；历史、模型规划和读取核验继续执行，不将历史纠正误作无历史查询。
- 无明确工具领域的聊天由原回答模型直接处理，保留工具权限、可靠性门和医疗质量地板，避免快速模型先生成后丢弃。
- 明确记录当前餐食且持久化 owner、原消息、全部图片与回执/卡片一致时，在共同收尾路径结束，不再等待额外模型正文。未知、失败、待确认、附加目标保留原流程。
- 后端不再把图片保存/正在写入进度算有效结果；Mobile v3 分离进度与内容/核验回执，API、统计、摘要和导出同步且不混入旧版本 first_useful。onLayout 仍不证明视口可见。

RED 路由/生成 9 failed、128 passed；最初缺 Pi runtime 的环境失败已单独保留，修复依赖后才确认 RED。食物实际 run_stream 的单/多图原先均多调一次模型；Mobile 六类进度原先均误报 first_useful。
定向路由/质量门 360 passed；食物 flag-on 289 passed / 1 skipped；Mobile 206 passed；后端指标 API/统计/导出 128 passed 与版本契约 17 passed。TypeScript、System Map、秘密扫描、语法/未定义名 Ruff 和 diff 检查通过。CI-mode 合并集成、G4 与发布闸待完成。

真实模型配对用两个固定合成聊天任务各两次，原回答模型固定为自动 qwen3.7-plus；同一 Pi/Gateway，临时同意主体与 SQLite，路由服务两组均关闭以隔离模型重复生成。基线四次均为 Qwen Flash→Qwen Plus，两次调用；候选四次均一次 Plus。完整时间中位数 17.27s→5.04s，P95/P99 最近秩最大值 20.59s→7.65s；四次均成功，两组均 0/4 在三秒内。完整单样本和脚本见 [机器证据](../reviews/2026-11-03-agent-pipeline-performance.json)。小样本不可外推生产长尾；只证明该调用路径少一次生成，不证明普遍达到三秒，也不将调用数下降等同人民币成本同比下降。

后续上下文装配、视觉服务时延及复杂分析生命周期继续按同样证据门推进；本批不引入新的缓存、视觉模型或后台任务机制，不以重构文件数量冒充时延收益。原始深度分析/视觉慢样本和三秒验收仍保留，未宣称完整规划全部交付。


第六轮最终候选 `b9904bd198615e811b4c6df3d586e537431d53e6`：CI-mode 合并集成 859 passed / 1 skipped，真实 PostgreSQL 17 的食物核验 38 passed，独立 G4 470 passed / 1 skipped 与 Mobile 206 passed，判定 GO。精确候选真实模型闸 invariants 12、health core 50、live orchestrator 5（均分 0.92）、trajectory contract 12、goldens 9 全部通过；未降低质量门。

- [完整 CI 41589056536](https://github.com/itsoso/health-llm-driven/actions/runs/41589056536)：32/32 成功。
- [发布预检 41590621462](https://github.com/itsoso/health-llm-driven/actions/runs/41590621462)：成功。
- [后端发布 41593274202](https://github.com/itsoso/health-llm-driven/actions/runs/41593274202)：成功。独立读回生产 SHA 和干净工作区一致，backend `SUCCEEDED`，runtime `COMMITTED / code-only-no-backup`，lease 已释放，backend / worker / beat / Laya 正常，内外网健康通过。backend 回执 SHA256 `3af956d568c336509b2dba613be13fa605613fe594b9e7fc34d067864737313c`。
- 后端初次调度在获取工作流信息的 GET 阶段 TLS 超时；原意图和错误保留，经独立任务列表及服务器回执确认未提交后，续接原意图并只创建上述一个部署任务，未重复消费发布。
- [OTA validate 41593940381](https://github.com/itsoso/health-llm-driven/actions/runs/41593940381)：成功。

- [OTA publish 41594210824](https://github.com/itsoso/health-llm-driven/actions/runs/41594210824)：成功。OTA `SUCCEEDED` 回执 SHA256 `89237f5fd068e34c6345c70e0b0a3134c946fc79f42f0f8cc8cd08c0bff5f5b6`；intent 和 verified receipt 的摘要关联已独立复核。
- 公开 iOS production 清单独立验证通过：runtime `1.3.6`，group `31d07b8d-d6ab-4ed6-a5c8-8515f4bef826`，update `01a1a043-3b71-7369-b6c5-5ae35d80bd77`，launch asset 与全部 47 项资源摘要一致。发布后生产版本及健康保持正常，lease 已释放。

第六轮首批优化 G5 发布完成，G6 自动线上发布核验 PASS。模拟器实际界面、设备 OTA 接收和生产 v3 有效结果 P95 仍未验证；4 个合成聊天样本的中位数下降不等于所有请求三秒达标。上下文装配、视觉首卡与复杂分析的后续阶段仍按规格分批推进，未宣称完整规划全部完成。机器交付证据与所有性能样本见 [本轮证据](../reviews/2026-11-03-agent-pipeline-performance.json)。


## 第七轮：饮水记录与已有计划的冗余模型等待（实施中）

用户要求继续优化，基线为 `5e4448dc547b7366484440c7a509ff9cfa823246`，生产代码为 `b9904bd198615e811b4c6df3d586e537431d53e6`，沿用既有隔离工作区与 Harness `ff67fa8caa7a`。新七天脱敏查询有 160 个 run；上一轮发布后仅一个有效新样本，不能形成生产分位数。该样本完整耗时 14.78s，可选 routing 5.18s、system prompt 184ms、history 17ms；先处理有证据的串行等待，不先重构上下文。

只读执行真实 Laya 路由探针，两类固定合成请求各两次，不执行健康操作：饮水记录路由墙钟 1561/262ms（均 abstained），已有计划 534/280ms（均 partial，capability none）。这不是端到端或生产 SLO。实际 executor RED 发现水量/日期已编译但 Pi 首轮仍调用模型；今日计划虽不需要模型也仍调用 advisory router。初始 pytest 使用保留参数名导致的 collection error 单独保留，修正后两条行为测试真实失败。

本轮目标：当前轮明确、完整的 typed 饮水记录复用普通 Pi/Gateway 执行已编译参数；已有今日计划读取与满足安全条件的饮水记录不先等待可选路由。保留临床质量地板、当前 owner/date、缺量澄清、确认、幂等、失败/未知回执、写入禁止和原通用完成流程。附件、附加目标、历史纠正与不明确请求继续原路径。不新增缓存、通知、权限、配置或数据库结构。停发条件为错误写入、绕过确认/质量门、伪造成功、成本或尾延迟恶化；不恢复旧配置或执行备份。


初版负例发现“一杯水”的容器默认量和“记录喝水并分析睡眠”的复合目标也有 simple goal，不能据此跳过模型。快捷入口已加完整当前轮语法、明确数值/单位和单一请求边界；25 项 PostgreSQL 17 用例通过，覆盖 owner/date、幂等重放、失败/缺回执。综合 CI-mode 回归 892 passed（222.12s），随后恢复原有晚期参数编译位置作为再次校验，最终 PostgreSQL 25 项重新通过；仅路由预览提前，不提前执行。System Map、Ruff 语法/未定义名和 diff 检查通过，最终扩大定向测试与 G4/发布仍待完成。

真实模型配对保留两轮×两类固定合成任务与所有失败记录，main-model 两组均关闭 optional route 以隔离提案调用。基线饮水 3893/1607ms，各一次 Qwen Flash 调用；候选 803/288ms，零模型调用，各一条 verified 写入回执。已有计划两组均零主模型调用，本地约 8–15ms，路由节省只由独立真实 Laya 样本证明，不与上述耗时相加。基线首轮诊断脚本读取未设置的上下文属性失败，虽业务已完成仍完整保留为测量失败，修正诊断后重新完整运行，未选最快结果。样本仅说明该窄路径，不证明生产 P95 或所有请求三秒内。完整脚本与样本见 [本轮机器证据](../reviews/2026-11-03-closed-water-route-performance.json)。

最终源码的定向检查先有 156 passed / 1 failed：新增的“喝了0.5升水”探针未形成既有已编译 goal，应保留普通路径而非视作快捷支持；已改为负例，并验证既有解析支持的“记录喝水0.5升”。修正测试预期后的 13 个相关变体全部通过，未扩大 goal 解析或授权。


独立 G4 对 `d88f0b4ca` 判定 NO-GO，未 push：原文四空格/Tab 缩进的记录语句被 strip 提升为闭合提案，真实 Pi 两例均新增一条水记录；“请帮我喝水/请喝水”仅证明误入路由快捷判断，后续原授权阻断落盘，不能误写为已证实越权写入。父流程补充六个真实流反例全部 RED。修复保留原始输入、拒绝缩进/多行/Tab，要求明确记录动词或已完成的“喝了”事实，且原有 compiled goal 与全部运行边界仍为必要条件。初次候选真实模型闸虽通过，不能覆盖该安全 BLOCK；修复后重新验证及独立审查。

修复后的 PostgreSQL 17 全部 34 项快捷路径/拒绝边界/幂等/失败用例通过，包含真实 count 断言证明非闭合输入不产生新增水记录。独立 SafetyGuardian critical 与筛查异常两例均验证流式及保存正文存在安全提示，零模型且回执完整。


第七轮修复候选 `147eef28f03d38e1c41fc42f8c2735828ad063c6` 的 CI-mode 集成 901 passed，最终 PostgreSQL 34 passed，精确候选真实模型质量闸通过。新独立 G4 判定 GO：135 项原套件、40 项独立边界/安全探针、3627 项权限/同意/计划/补记测试通过；SQLite 下三项既有 PostgreSQL 锁语义测试跳过，不以其证明并发。最终配对饮水复测 854/291ms，均零模型调用并有 verified 回执，对照 3893/1607ms；两样本中位数 2.75s→0.57s，不是生产长尾或设备显示验收。

该候选已推主干，完整 [CI 41613609960](https://github.com/itsoso/health-llm-driven/actions/runs/41613609960) 的 balanced-09 在 `test_full_pi_initial_request_preserves_authoritative_schema` 失败：旧断言要求闭合饮水请求必须调用模型。原失败保留，未进入 staging、授权刷新/轮换、后端或 OTA。修订该测试覆盖优化关闭、开启 typed、开启 voice 三种实际 Pi 路径：均核验 authoritative schema 完整；需模型时保留 provider schema 一致断言；闭合 typed 路径要求零模型、完成状态及一条核验回执。最终该文件 28 passed，独立审查确认未削弱工具 schema 边界。早期复合请求测试夹具未经过含 health_record 的 Pi 工具选择，出现 StopIteration，已保留并以真实开关/通道边界替换；未修改应用实现以迎合旧断言。

修订测试后的 CI-mode 四文件集成 385 passed；新增 voice 变体另行连同整文件 28 passed。原 GitHub CI 已终止：29 项成功，分片09及其两个汇总门失败，未发现第二个独立失败。新候选须重新经过精确主干完整 CI 与发布门，不重跑原失败回执冒充交付。


### 第七轮发布收尾（最新状态）

最终候选 `2dddb4c560db5c04315bdae2f7d95fcccd421bad` 与已测 `147eef` 的整个 `backend/app` tree 相同，增量只有测试和证据。独立 G4 再次绑定新 SHA 判定 GO；精确候选真实模型质量门全部通过（live orchestrator 5/5，均分 0.90），未使用 waiver。先前失败 CI 与负例日志保留，没有部署失败候选。

- [完整 CI 41615158481](https://github.com/itsoso/health-llm-driven/actions/runs/41615158481)：32/32 成功。
- [发布预检 41616754692](https://github.com/itsoso/health-llm-driven/actions/runs/41616754692)：成功。canonical staging、只读凭据刷新和授权轮换分别经过独立固定脚本审查并单次完成；无备份、无旧配置恢复。
- [后端发布 41619395908](https://github.com/itsoso/health-llm-driven/actions/runs/41619395908)：成功。独立读回精确生产 SHA、干净工作区、`SUCCEEDED` 回执、backend / worker / beat / Laya active/running、内外网健康与 lease 已释放。backend 回执 SHA256 `6c945f2bed933be1b5efb7767fb2d6b6aca3124f0249f8ac6f53e4cc40717f47`。本次 runtime **journal** 为 `COMMITTED / code-only-no-backup`；独立 terminal 文件仍保留前次记录，不将旧 terminal 冒充本次证明。
- [OTA validate 41620191437](https://github.com/itsoso/health-llm-driven/actions/runs/41620191437) 与 [OTA publish 41620501051](https://github.com/itsoso/health-llm-driven/actions/runs/41620501051)：同一精确候选依次成功。OTA `SUCCEEDED` 回执 SHA256 `2027c6caa513ca58a0309ddf136acc9cd04e8080cb135a525184029cbf16ae18`，intent 与 verified receipt 摘要关联一致，lease 已释放。
- 公开 iOS production 清单独立通过：runtime `1.3.6`，group `e39c4e5b-f9a9-49f0-a5ce-1dc9555fa6c6`，update `01a1a101-3792-788a-88f5-3667b222ddc9`；launch asset 与 47 项资源摘要一致。本轮业务改动仅后端，按本会话用户持续明确的发布与 OTA 指令完成同版本发布，未新增 Mobile 运行行为。

G5 发布完成，G6 自动线上发布核验通过。合成饮水两次中位数 2.75s→0.57s 只证明明确完整 typed 饮水路径的提案模型调用被省去；生产长尾、模拟器实际显示、设备接收仍未验证，不能宣称所有请求三秒达标。完整样本、失败、修复及发布证据见 [本轮机器证据](../reviews/2026-11-03-closed-water-route-performance.json)。

### 第八轮：化验事实提前展示（2026-11-04，已发布；三秒目标未达成）

最新 main `f0a520a4eb547b9e230b73a5443f4620180aea92`，生产 `095ef6936552121264524fc5d537fa783adf8b5b`，沿用隔离 checkout 与 Harness。七天脱敏只读统计158个run，仅一个新样本：完整171926ms，服务端首内容113040ms，三次模型调用合计157655ms，可选路由5031ms；工具为 health_query / knowledge_search，不是重复调用证据，未保存具体参数，不能把它断言为某个医疗查询路径。原始 prompt/健康载荷未导出。

只读独立调查确认普通 medical_exam 的纯文本结果缺少结构化事实投影，而已有提前 GenUI/依据出口可复用。按[本轮准入与契约](../specs/medical-readout-early-facts.md)补最小展示切片，不调整模型选择、临床思考或权限。目标为成功读取后、下一模型调用前提供事实；长期三秒目标仍未达成。保持原临床文本、owner/日期/筛选绑定及来源局限，失败/范围不符不得出卡。新行为三个RED，13个拒绝边界已通过。

真实模型基线先因工具白名单未含 query_lab_indicators 停止，完整保留为测量失败；修正探针范围并固定报告查询请求后重新测量，不删除失败记录。后续同一请求与合成数据成对验证；样本量不足不报告生产长尾。

本轮实现新增同查询数值投影，原 canonical reader 默认文本不变；Agent 展示和依据使用投影，模型通过既有 model-only result choke point 得到逐字原 summary，避免重复上下文。补充不完整 envelope 拒绝和模型文本不变四项 RED 后全部通过。CI-mode 相关集成626 passed，最终 PostgreSQL60 passed（含所选报告隔离）；Ruff fatal、diff及重新生成后的System Map通过。

真实模型探针的前几轮存在测试环境限制：未允许既有 medical_exam report-list GET，以及报告列表未接合成用户的本地API，导致提前停止/失败，两组均受影响。未据此宣称性能退化或改善，全部日志保留；最终探针改为仅允许原只读工具与医疗报告列表，并以真实JWT鉴权的ASGI API访问同一临时数据库，禁止其他HTTP路径和任何写工具，模型调用上限5次。最终配对和独立G4仍待完成，尚未发布。

独立G4对 `22c097df3` 判定NO-GO：跨午夜的冻结日期与服务器日期不一致，或原工具参数有 `days=None/limit` 等非投影形状时，数值卡正确拒绝，但模型收到额外JSON，违反原文不变的质量底线。未发现越权或临床原文丢失。父流程补RED，修复先用原始 supplied_args 决定是否opt-in，再在序列化端按实际日期差校验窗口，不匹配直接保留原文本；禁止放宽卡片验证。首次修订误在归一后的args做门控，仍有三个RED，已修为归一前参数。另处理等价只读缓存重放：模型文本提取沿用已有只读去重的参数归一，保持原summary，卡片仍按原执行范围校验；该行为先RED后GREEN。极早日期使用日期差避免减法溢出。

修复后CI-mode集成620 passed，缓存边界修复后相关155 passed；最终PG及新独立G4待完成。有效ASGI配对请求均成功：基线首流出内容17141/20043ms，候选3752/5999ms；完整回复17194/20066ms对24810/16443ms，候选第一例多一次模型规划。此数据只证明该事实展示切片能先于完整回复出现，不证明完整耗时、成本或生产P95改善，更未达成三秒SLO。正常查询的模型结果原文逐字不变；不将模型随机轮次数差异归因于这次展示变更。全部失败探针、样本与证据摘要见[机器证据](../reviews/2026-11-04-medical-readout-performance.json)。


第八轮最终闭环：候选 `829110cdfc89fd5972355653da57bf6773da249e` 修复后 PostgreSQL69 passed，独立G4 GO（113项回归、4项旧边界、真实Pi历史/缓存/流式一致性1项、15项恶意输入探针）。精确候选 live Gate 通过；[完整CI41744438892](https://github.com/itsoso/health-llm-driven/actions/runs/41744438892)全部32个job成功。首次本地change-gate调用缺少GITHUB_SHA而配置失败，补齐精确候选环境后通过，原失败保留。

[后端41748420298](https://github.com/itsoso/health-llm-driven/actions/runs/41748420298)成功，生产HEAD为829110cdf且干净；runtime事务COMMITTED、业务租约释放，后端/worker/beat/Laya active/running，内外网健康检查通过。canonical staging、只读App凭据刷新及独立审核后的授权轮换均保留一次性回执，没有备份或回退副本。

[OTA validate41749160627](https://github.com/itsoso/health-llm-driven/actions/runs/41749160627)通过后，[publish41749446880](https://github.com/itsoso/health-llm-driven/actions/runs/41749446880)成功。服务端完成回执与公开manifest一致：production/iOS/runtime1.3.6，group `a62501a2-fcf7-412e-b113-dcb8656f28f8`，update `01a1a40d-917d-7abe-8f6c-717531ff3d91`，启动制品和47个资源哈希匹配。两端均为同一精确候选，发布后无业务租约。

配对合成请求首个服务端内容中位数18.59秒至4.88秒，完整回复并未稳定变快。每组仅两例，不证明生产P95/P99、成本改善或三秒SLO；没有把最新线上172秒样本与合成4.88秒直接比较。App实际绘制、设备接收及真实用户新查询验收尚未验证，不能把公开manifest成功等同设备验收。最终证据已补入同一机器证据文件；本轮代码发布完成，整体性能目标仍待继续。


### 第九轮：日常对话输入预算（2026-11-04，实施中）

用户批准最近两周分析方案后继续开发部署，沿用已授权隔离 checkout 和同一 Harness run。基线为 ad8949e7e；原共享工作树未动。[准入与契约](../specs/everyday-prompt-budget.md)限定完整正向语义，不以未知短句或空 pending 列表判定普通聊天。

新增日常路径仅省略已证明无关的健康工具、全量系统上下文、可选决策与知识/Twin预加载，保留用户选定模型、原历史构建、源时间/消息来源、终态验证与落库/流式文本一致性。完整小会话按 owner 查询；达到普通历史窗口上限即不准入，不用尾部问候覆盖更早待办。问候、致谢、闭合接车观察、无开放主题的短故事/笑话为当前覆盖；未知自由文本和任意旧助手叙事仍走原路径。

Provider wrapper 新增纯数字 prompt_payload；真实 API token/cached token 不被字符估计覆盖，失败/取消/fallback 各调用独立计量，capture尾部上限及遗漏项显式返回。无新DB字段、无健康原文/参数/URL导出。完整JSON工具示例只省少量字符，本轮未为此泛化删除安全说明。

辅助模块69项通过；实际Pi provider载荷先4 RED（仍携带全套工具），接入后通过，补原始更正历史后8项通过。首轮环境缺Pi依赖和一次编辑瞬态语法错误不计行为RED，后续已修正；非流式metadata coverage有独立RED后GREEN。CI-mode相关289 passed。独立临时PostgreSQL86 passed；首次PG暴露测试硬编码缺少user FK，修为真实创建合成用户后重测通过。System Map生成物已同步，检查通过。更广回归、配对真实模型、独立G4和发布尚未完成。

发布约束：并行原生41806221746终态failure，但iOS构建和TestFlight上传成功，backend重复消费失败；其活动claim尚未收口，旧OTA基线亦不兼容主干原生变更。继续本任务验证，不绕过原操作与OTA闸，不把本地代码称为上线。


第九轮扩大CI-mode490 passed，临时PG86 passed。真实模型配对[机器证据](../reviews/2026-11-04-everyday-prompt-performance.json)：生产既有domain开关双方均True，基线仅关闭新准入；三组请求各两次，12/12成功且仅用户选定DeepSeek单次调用。输入API token为12,175→545、12,175→542、12,294→663，缩减94.61–95.55%。候选实际释放首token1.34–2.68秒，中位2.56→1.94秒；完整中位2.58→1.95秒。基线缓存11,776/次，候选零缓存，输出长度不一致；不能当纯prefill因果或生产P95/设备呈现证据。初始off/on探针仅探索，不混入归因结果。最大14条原历史加当前消息的实际Pi载荷保留全部原文和更正。后续main分享UI已在隔离分支无冲突合并，后端受测源码摘要一致。


第九轮发布续接（2026-11-05）：前序分享 UI 已于 91b1f1ed 完成后端与 OTA，随后生产推进至 c616a38d；本轮与该已发布 Mobile/shared 树完全一致，不重复发布空 OTA。整合最新主干得到 bbefd3a97，独立新鲜 G4 GO（175 项回归、12 项实际 Pi 探针）；鼻症状、餐次澄清与待补食物历史均不能进入 everyday，原始更正和正常写入边界保留。精确真实模型闸通过，System Map 通过，PostgreSQL 213 passed、pytest exit 0。临时 PostgreSQL 关闭等待超时使外层 runner exit 1；原关闭随后正常完成，独立确认进程已退出，未掩盖此清理异常。

PR #305 已合入 main。bbefd3a97 的完整 main CI 41982384643 为 32/32 success；同 SHA 的 PR CI 41982348463 被取消为重复验证。validate 41983648177 在 canonical source/CI 首步失败：发布闸要求该 SHA 的所有 CI 都来自 main，同 SHA PR run 因身份不符被拒绝，即使其重跑通过也不满足来源要求。未进入 dispatch admission、生产凭据或部署；原失败保留且不重试。canonical staging 单次成功，无授权轮换/部署。

采用已有症状发布相同问题的处理路径：以本段验证证据形成仅推 main 的文档后继，应用字节保持不变，重新绑定精确 live gate、完整 main CI 和新候选 validate；不放宽发布闸、不删除 CI 记录。当前生产与授权仍是 c616a38d，服务正常、无发布 lease，优化开关在三个进程均为 true；只读 GitHub 凭据已过期，须新候选固定刷新审查后继续。此时尚未部署本轮优化。


第九轮最终发布完成（2026-11-05）：发布候选 `22547e0cec309cf32821b94263cbad3b629a584b` 的应用/发布器字节与已审 bbefd3a97 一致；精确 live gate 再次通过。[完整 main CI 41984242004](https://github.com/itsoso/health-llm-driven/actions/runs/41984242004) 32/32 成功，文档 push CI 41984226906 同为 main/success；[validate 41985372405](https://github.com/itsoso/health-llm-driven/actions/runs/41985372405) 成功。固定 canonical staging、受审只读凭据刷新、成功旧授权 c616→225 轮换均有单次完成回执，不重试旧 bb 失败预检，不新建备份。

[后端发布 41987030790](https://github.com/itsoso/health-llm-driven/actions/runs/41987030790) 成功。独立生产回读 PASS：HEAD 精确且 clean，回执 SUCCEEDED（摘要 `7077d33b65fc1dc20776de470769f577a752d4cf0a57d2f44702f70f66acb869`），runtime COMMITTED/finalized/code-only-no-backup，lease 已释放；backend/worker/beat 全 active 且 DOMAIN_PROMPT_OPTIMIZATION=true；内外 health 200，受保护匿名接口 401；八项运行时源码摘要与候选 Git 对象一致，合成纯路由正反例通过，无健康 DB 写入或模型调用。完整证据已回填[机器证据](../reviews/2026-11-04-everyday-prompt-performance.json)。

本轮 Mobile/shared 树与已发布 91b 完全一致，沿用其 OTA 41822477785 / group `5e241435-e16f-49c1-a45b-cf6e54f52ea3`，未重复发空 OTA。代码发布与线上运行核验完成；真实设备呈现和生产请求 P95 未测量，仍不能把合成样本 1.34–2.68 秒外推为所有日常对话均小于三秒。


## 第十轮：普通单餐建议误报个人查询失败（2026-11-05）

用户截图中，天气问答之后的“今晚吃点啥比较好”被替换为“本轮数据查询未完成”。
代码回溯发现 current-input advice 已覆盖多领域日程草稿，但未覆盖完整的单餐选择问句；
额外的无授权个人读取被 Gateway 拒绝后，无法证明原问题是无需读取的建议，触发查询失败终态。
本轮沿用 quick_fix + safety-gate；这是既有通用建议行为修复，不新增个人数据权限。

新增封闭的整句单餐建议语法，复用现有 current_input_local_advice 入口，提供经过审查的
通用餐食组合、过敏/不耐受/医嘱限制及澄清追问。不读取记录、不调用模型、不创建饮食或计划；
回答明确未做个体化调整，不能把历史或天气当作营养依据。公开食物组合依据为 NHS Eatwell Guide
（2026-11-05 核验）；不设定热量、减重目标或固定摄入量。

额外症状、个人记录依据、过敏限定、第三方、引用、否定、写操作、未知残留仍走完整链路。
附件和不确定写恢复保持原顺序；持久化失败不发成功，跨账户对话拒绝，重放保持原文。
该修复不扩大 everyday prompt lane，不更换用户所选模型，不移除真实查询的证据闸。

验证：截图原句先 RED（is_current_input_advice=False）；初轮含相邻测试 186 通过、2 项因
隔离目录缺 Pi node_modules 失败，接入同版本本机依赖后扩大回归 294 通过。
新增附件与自由模型文本拒绝测试纳入后续 PostgreSQL 回归。System Map 全闸通过，未产生架构漂移。
PostgreSQL runner 初次因临时脚本替换了测试文件名而收集失败，已正常停库，修正测试清单重跑。
独立 G4、精确主干完整 CI、生产部署和发布后验收尚待完成。Mobile 无变更，按部署规范不发布相同空 OTA。
仅零模型路径验证不等于手机三秒体验或生产 P95 达标。


### 第十轮 G4–G6 与生产交付

- 固定候选 `caba0b029e9033df51a387d635a5904cd78c6e3e` 独立 G4 GO：193 项回归，
  5 正例与 164 对抗反例通过。PostgreSQL 非超级用户 228 项通过，临时集群正常停库、runner exit 0。
- 精确候选真实模型回归闸通过（82.77 秒，仅合成主体/内存测试库），对应 CONFIRMED 已绑定；
  System Map、秘密扫描、diff 检查通过。实际单餐建议入口无需模型，不把该门耗时当 App 延迟。
- 当前 main push 完整 CI `42005779104` 32/32 success；trusted validate `42007485071` success。
  canonical staging、固定凭据刷新、旧成功授权退休及新授权安装均有独立审查和一次性完成回执。
  全程沿用 no-backup 发布契约，未重放失败/未知发布。
- 后端 `42009247178` success，独立线上复验 PASS：生产干净且精确为候选；SUCCEEDED 回执，
  runtime COMMITTED/finalized，原租约释放。backend/Celery worker/beat 稳定 active，优化开关仍 true。
  内外健康接口 200，未认证个人接口 401；9 个源码摘要与本地候选 Git、服务器 Git 和运行磁盘一致。
- 生产纯合成分流探针 5 正例/10 反例通过，探针禁止外部 I/O，不读写用户数据或调用模型。
  本地真实入口已覆盖天气与失败查询历史后的回复、streamed=persisted=replayed、无工具/无写回执。
  这不等于使用真实用户账号做了端到端验收，也未测手机界面或生产 P95/三秒 SLO。
- Mobile tree `55e77507ff757956823de4861e87bad842b62eb4` 与既有 OTA `91b1f1ed…` 完全一致；
  无客户端修改，按适用边界不发布空 OTA，现有 App 使用新后端。合入的发布证据文档后继不需要重复部署。

机器证据：`docs/reviews/2026-11-05-meal-suggestion-release.json`。
部署工作流：https://github.com/itsoso/health-llm-driven/actions/runs/42009247178。
