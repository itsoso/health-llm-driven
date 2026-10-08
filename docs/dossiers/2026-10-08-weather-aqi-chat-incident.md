# 天气与空气质量组合查询故障

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 验证与独立审查 |

- 日期：2026-10-08
- Controller：health-harness-orchestrator（incident），safety-gate overlay。
- Harness：`6dcf36a10fa2`。
- 接手基线：`549765a95a5011cb06bd62fe28d669d3f2991892`；此前后端发布：`9b05c5c9ef27b5401b6b31b37892c28ed1d1ec2c`。
- 当前状态：公共天气修复已在 main `e59fd935a6f73bb43d330a9db3602ad8807e01f8`，完整 CI 29 项通过；发布前发现重启中断机制，补充 G3/G4 验证中。生产仍为 `9b05c5c9ef27b5401b6b31b37892c28ed1d1ec2c`。下文未合并/未定位记录为当时阶段证据，以末尾续记为准。

## 用户验收与边界

截图请求为“杭州明天天气温度怎么样？空气质量。”，却返回模型不可用及“没有生成可靠健康建议”。应回答核实的明天天气与温度，明确空气质量是当前观测、不能冒充明日预报。服务失败如实说明，不能制造天气、成功回执或健康建议。

保留其他 session 的饮食性能改动及既有写权限、健康安全、附件和待确认上下文边界；不启用被真实模型回归否决的写工具说明压缩。本次仅后端，无移动端或原生发布变更。

## 已证事实与未决根因

- 生产窄时间窗日志及按认证所有者限定的只读元数据表明：模型首轮成功，返回两个工具调用，随后执行器捕获 `RuntimeError`；没有工具请求/执行记录。未输出消息原文、健康载荷、密钥或异常全文。
- 不能由该日志裁决模型宕机。原日志仅记录异常类型，不足以定位内部失败。
- 当前生产进程与 CLI 身份密钥仅检查长度布尔值，均符合最小长度；不能将合成短密钥实验认定为生产根因。
- 合成真实 Pi 两工具可完成；畸形参数可能在 Node 拒绝后进入第二模型轮，因此一个已完成 round 不排除下一轮早期失败。
- 两次初始真实模型基线未复现 RuntimeError，但 domain_prompt_optimization 与生产配置不同，仅作诊断，不用来作严格性能对照。
- **历史 RuntimeError 尚未闭合根因。** 以下为有测试证据的独立缺陷修复，不能将路由变化等同于解释历史异常。

## 已实现

1. 闭合公共问题语法覆盖天气温度与空气质量组合；由服务端编译同城天气/预报和当前 AQI 两个读取，经原工具网关执行，再单轮模型合成。
2. 空气质量载荷和公共提示明确当前观测而非未来预报，保留不可用数据拒绝条件；工具失败终止合成且最终状态为 error。
3. 通用失败文案不再臆断发生健康建议任务；未知内部异常不再冒充已确认的模型服务宕机。额度、限流、超时仍保留明确类别与重试指引。
4. 异常日志增加单一应用代码位置（模块名与行号），不输出异常正文、绝对路径、源码、局部变量或整段堆栈；移除该日志中的原始用户 ID。

## 验证

- 公共组合路由：RED 4 failed / 66 passed；实现后邻近测试 90 passed。
- 错误文案：RED 5 failed；代码位置辅助函数 RED 1 failed / 5 passed；实现后与额度测试 14 passed。
- 整合回归：416 passed，包括真实 Pi 协议、公共路由、危机语言安全与额度控制；不把合成环境读取当真实天气服务验证。
- AQI 不可用最终状态断言已通过；现有结果归一化已返回 error，不需要额外状态补丁。
- System Map 校验通过。
- 正式 `harness_llm_regression_gate.py --include-live-llm` 等价程序入口通过；10 次 API usage 调用均成功、源码哈希未变。证据：`docs/reviews/2026-10-08-weather-aqi-live-regression.json`。此通用健康回归不替代截图原句专项验收。
- CI-mode 集成 21 passed；同生产 domain_prompt_optimization=True 的专项真实模型配对两案通过，见 `docs/reviews/2026-10-08-weather-aqi-paired.json`。基线输入 23003/23329 token、各两次 qwen3.8-max 调用；候选各 685 token、各一次默认 MiniMax-M2.5 调用；耗时 9.61/8.52 秒 → 5.24/4.09 秒。收益包含路由模型变化，不是同模型纯压缩对照；仅两例、合成公共数据，不代表线上 P95 或天气真实性。候选均正确区分日期、18–24℃与当前 AQI51，明确无明日 AQI 预报。基线额外健康/户外建议被人工判为偏离任务，保留该失败。固定提交独立 G4、精确 SHA CI 与发布仍待记录。

## 发布与剩余验证

本次尚未合并或部署。不宣称历史异常已完全排除；必须分别记录代码修复、真实模型质量、CI、生产终态回执和用户路径验收。

## G1 既有行为修复准入

裁决：PASS。修复既有公共环境查询的组合表达漏路由及错误文案，不新增 Health OS 对象、数据接收方、个人数据读取授权或写权限，不新增产品入口。用户原句及健康上下文隔离、天气真实性、日期边界是验收标准。

## 独立审查发现与整改

- 固定候选 `19cd262b9`（运行时同 `96133ef49`）首轮独立安全审查 NO-GO：公共 AQI 分支透传了服务附带的健康/运动建议，而此前合成样本不含这些字段。未推送该候选。
- 改为公共路线的观测字段 allowlist；不改健康路线的通用环境服务。含建议哨兵的 payload 与完整 provider 输入测试 RED 2 failed / 89 passed，修复后通过。
- 生产公共环境读取确证 qweather-v1 `update_time` 为不透明缓存标签，不是时间。公共投影剔除无效时间并显式标记未知；提示禁止以系统时间替代。时间验证 RED 8 failed，修复后通过。未存放实际标签值或个人数据。
- 修复后 425 项相关回归、21 项 CI-mode 集成、System Map 通过。新正式真实模型回归 10 API 调用通过，源码哈希匹配：`docs/reviews/2026-10-08-weather-aqi-final-live-regression.json`；保留前一版本证据，不覆盖失败。
- 含五类健康建议哨兵、分别有效时间与不透明标签的两案真实 provider/Pi 验证通过，输入 716/707 token，耗时 3.77/3.88 秒。观测事实保留，建议与标签未进入模型，第二案明确来源时间未知。见 `docs/reviews/2026-10-08-weather-aqi-projection-live.json`。
- 此新证据替代前版 685 token 作为当前候选值；语义与载荷不同，不把两次延迟直接归因于投影改动。当前接口类别不证明实际数据新鲜度；第二案措辞含“实时”同时注明来源时间未知，独立复审核对中。
- 截图历史 RuntimeError 仍未定位；当前发布范围是已证公共组合路由、错误文案与观测投影缺陷。尚未合并或发布。

## 观测时点二次整改

- 固定 `0dbda6322` 再审 NO-GO：原第二案的“实时数据”与来源时间未知矛盾。前一证据的自动检查虽通过，人工语义裁决为 FAIL，保留原回复与证据，不以局部测试通过代替语义通过。
- 公共载荷标记改为 `air_quality_observation_not_forecast`，不暗示观测新鲜度；提示要求时间未知时不得称空气质量为实时、最新、今天、此刻或当前，并明确无法确认观测时点。
- 新 RED 2 failed；修复后 426 项相关回归通过。新两案真实模型验收通过，见 `docs/reviews/2026-10-08-weather-aqi-freshness-paired.json`：有效日期保持来源精度；未知时间仅报告 AQI 观测值并声明时点未知，无额外健康建议。
- 最终候选两案 API 输入 741/732 token、各一次模型调用、耗时 6.06/4.99 秒。此值取代前述中间候选指标。两案均合成公共观测，不作实际杭州天气、生产 P95 或历史异常根因证明。

- 最终 21 项 CI-mode 集成与 System Map 通过。正式真实模型回归 10 次 API 调用全部成功，34 个源文件哈希与最终运行时一致：`docs/reviews/2026-10-08-weather-aqi-freshness-live-regression.json`。该轮开始时 runtime 已修改但尚未 commit，故以文件哈希与最终提交逐一匹配，不把报告中的起始 HEAD 冒充当时干净源码。

## 发布重启中断机制与补充整改

- 原请求日志时间线：19:00:33 systemd 开始停止后端；19:00:37 同一旧进程首轮模型返回两个工具调用，随后 RuntimeError，零工具执行，紧接着完成应用退出。生产有效配置为 `KillMode=control-group`、SIGTERM、45 秒停止上限，uvloop 0.22.1。未记录任何健康原文或身份信息。
- 本地真实 Pi 子进程在模型等待期间被终止：uvloop 3/3 在 `stdin.write` 抛原生 RuntimeError；标准 asyncio 3/3 返回受控 PiKernelError。此结果与发布停止时间线吻合，定位为关闭期间工具子进程先于模型返回退出的机制，不能称为上游模型不可用。未复演生产用户请求。脱敏证据见 `docs/reviews/2026-10-08-pi-shutdown-reproduction.json`。
- Pi 对已退出/关闭管道及关闭竞态统一抛 `pi_transport_failed`，无自动重试；未关闭管道的未知 RuntimeError 和 CancelledError 保持传播，避免掩盖异常或重复写入。新增 RED 2 failed；修复后传输相关 22 passed。
- 后端单 worker 采用 `KillMode=mixed`：先仅向主进程发送 SIGTERM，由 Uvicorn 最多 30 秒排空请求，再在 systemd 45 秒上限下强制结束残留进程。配置由现有事务化 drop-in 发布，验证有效信号、范围与超时；保留原 journal schema 及恢复路径。
- 本地真实 Uvicorn/uvloop/Pi HTTP 对照：初始信号作用于整组时 3/3 请求失败；只作用于主进程时 3/3 完成且子进程回收。只使用合成回复、不访问模型或数据库，信号实验不冒充 Linux systemd 端到端验证。可重跑 `scripts/probe_pi_graceful_shutdown.py`；结果 `docs/reviews/2026-10-08-pi-graceful-drain.json`。
- 首次迁移限制：现有可信发布先停止旧服务再安装新 drop-in，因此本次旧配置第一次停止仍可能中断进行中的请求；新配置只保护其生效后的重启。不提前手工修改生产 unit，不绕事务授权。超过 30 秒的请求仍可能被取消，不承诺零中断。
- `e59fd935a` 已通过 push CI `37773119726`（24 success / 5 skipped）及完整 CI `37773170496`（29 success）。新增关闭修复须重新完成固定提交 G4 与精确主干 CI，不能沿用该绿色结果发布新代码。

- 关闭修复后的正式真实模型回归再次通过：10 次 API 调用均成功，35 个源文件哈希未变（包含 Pi transport），见 `docs/reviews/2026-10-08-weather-aqi-shutdown-live-regression.json`。System Map 使用仓库 Python 3.12 PATH 校验通过。
- 发布配置及恢复相关最终源测试 220 passed：六项有效 drain 配置篡改均被拒绝；无新增 drain 字段的旧 journal 仍能安装新配置并恢复原旧 drop-in 字节。

- 最终后端 CI-mode 相关回归 61 passed，包含既有 21 项集成、Pi 写入对账与关闭竞态；无自动重试、取消不伪装成功。

- 30 秒超时边界实验保留 FAIL/部分证实：真实 Uvicorn/uvloop/Pi 的最小 lifespan=off 服务在 30.159 秒退出，客户端断开且没有伪成功/重试，但取消处理与 Pi 主动 await/reap 未证实。见 `docs/reviews/2026-10-08-pi-drain-timeout.json`。不能宣称超时请求完整优雅结束；这是保留 `SendSIGKILL=yes`、`FinalKillSignal=SIGKILL` 和 systemd mixed 最终整组清理的必要理由。此实验不证明生产 systemd 45 秒终态，须由独立评审裁决验证边界。

## 关闭修复独立审查与旧版本恢复整改

- 固定 `6be2a3455` G4 **NO-GO**：使用真实 `9b05c5c9` canonical base 与完整旧 drop-in 的内存回放，恢复证明错误地按新 recovery source 要求新配置，报 `effective drop-in bytes differ`。首次新版本安装前失败必须能证明仍然完整旧 generation，不能让新版排空配置阻断合理恢复。未推送此候选。
- 独立审查 231 项测试通过但未覆盖该场景；此前旧 journal 恢复原字节测试不等价于完整旧 generation 的 contained proof。需补 RED 测试并按认证 production revision 的精确配置代际修复，拒绝任意旧新混合与被篡改配置，不执行历史代码。
- 审查认为 30 秒超时部分失败不单独阻断：按生产 systemd 249 文档，mixed 在主进程退出或 45 秒超时后向剩余整个 cgroup 发最终 KILL；必须保留并核验该配置，不宣称应用层主动回收已通过。
- 更广发布/回滚/activation 测试 362 passed，作为补充证据；不覆盖新发现缺口。

- 整改 RED：完整旧配置代际两组合 2 failed / 2 passed；修复仅在恢复证明选择两个受审的完整配置模板，按 canonical production source 精确匹配，不执行历史 Python，也不给正式 publisher 增加接受旧配置的开关。
- 完整旧模板与真实 `9b05c5c9` backend drop-in 逐字节相同；新/旧 canonical 与相反 live drop-in 混用均拒绝，六个有效信号/超时属性、三服务命令、额外可写路径及未知 canonical 字节均拒绝。旧 journal/版本/租约/终态/权限证明保留。整改后四套相关脚本测试 330 passed。
