# 手动选模首轮一致性与响应延迟

| 字段 | 值 |
| --- | --- |
| 状态 | in_progress |
| 当前阶段 | G5 已发布；G6 发布回读通过，三秒性能与设备验收未完成 |
| 工作流 | quick_fix + safety-gate → backend-deploy |
| 基线 | 5806a685d880cb258f2733fe40cef0a9849cc195 |

## 目标、范围与停止条件

用户选择 DeepSeek V4.1 Flash，但截图首轮为 Qwen3.6 Flash，总耗时约 8.5 秒。
本周优先性能，用户要求响应提升到三秒以内。按真实有效内容衡量，加载动画和空泛
确认语不算结果；首个有效结果与完整回答分别计时。端到端点击到显示仍须单独验证，
不能将模型接口耗时或后台埋点等同手机体验。三秒范围的异步澄清尚无答复。

本批只修手动选模首轮被无条件快路由覆盖，以及已验证 DeepSeek 工具能力未登记。
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
  真实模型整套平均耗时约 7.59 秒，这也是不能声称所有场景三秒完成的证据。
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

三秒目标仍未完成：冷启动样本 4.16 秒、复杂 Harness 平均约 7.59 秒，手机端端到端和
生产负载下的长尾未测。不得把这次发布写成性能全面验收通过。后续应先补网络连接、
供应商等待、生成与实际输出释放的分段证据，再选择下一项优化；不得靠空泛确认、
超时截断健康处理或降低安全/质量约束达标。
