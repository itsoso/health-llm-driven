# 日常安排问句被误报查询失败

| 字段 | 值 |
|---|---|
| 状态 | shipping |
| 当前阶段 | G4 最终整合复审 |
| Controller | health-harness-orchestrator / incident |
| Overlay | safety-gate |

## G1 范围准入

裁决：PASS。修复已有日常安排草稿行为；沿用 `2026-10-12-daily-draft-admin-model` 的产品边界。用户截图中的“今天如何运动 饮食和 睡眠”是如何安排的问句，不是已有记录统计。整句识别的安排请求只允许通用知识及有条件建议，不获得个人记录读取或计划保存权限。带个人依据、记录查询、他人、取消、引用、额外写操作的输入不按通用草稿处理。

## 诊断与基线

生产 PostgreSQL READ ONLY 查询定位截图原句，同 owner、同本轮，仅输出状态和耗时，不导出个人资料或对话历史。线上本轮耗时 76900 ms，模型三轮分别 4654 / 6601 / 63911 ms；四次工具请求全部被拦截，最终 `health_query_dimension_conflict` / blocked，运行 failed。现有草稿语法仅覆盖“规划/安排/制定……”命令式，未覆盖“今天如何……”问句，导致未进入建议工具边界；本轮查询失败保护正确阻止了无证据结论。

## 修复与验收目标

覆盖整句命令式与问句的共有日常安排语义，支持领域顺序、空格、连接词及问句语序。保留当前输入建议 prompt、个人读取/写入 Gateway 和完成保护，不通过隐藏失败横幅或伪造查数成功修复。截图原句在新会话和前轮失败的会话中均应从现有 current_input_local_advice 终态直接回答，不加载私人上下文或调用模型/工具。附件、未闭合个人依据或额外动作不进入本地回答；其 Gateway 和发布保护保持严格。

性能底线：消除错误个人查数及其重试，不降低模型质量，不新增缓存、成本类型或付费资源。生产样本 n=1 只能证明本次失败轨迹，不能作为 P95/P99 改善证据。验收分别记录脚本 provider 控制流、PostgreSQL、真实模型及生产发布；未知不当通过。若出现越界读取/写入、虚假已查数或质量退化，停止发布并修复，不创建备份或回退副本。

## 验证记录

System Map 对 executor 无索引，统一 system-map-check 已通过，随后读取实际 executor、scope、Gateway 与邻近测试。保留其他任务未提交文件。单一 trace：`92084e21f6d0`。

G3：原语法 7 个新增问句失败；真实流未限制个人工具；旧 panel 测试假设被既有健康建议缓冲路径改变，改为验证公共 run_stream 的客户端 panel 请求和真实保存/流一致性，不强制绕过缓冲进入 panel。首轮测试环境连本地 PostgreSQL 未启动及 TEST_DATABASE_URL 格式错误均保留，不计行为证据。最终关联测试 278 passed，PostgreSQL 41 passed，隔离实例正常停止。新增 Prompt 边界测试先 RED，再约束未查数说明、不默认主食减半/热量缺口、不凭钟点保证睡眠；初次模型回放发现限制性饮食建议；原始完整输出文件因临时脚本复用发生覆盖，不能声称已完整保留。仅首轮调用元数据日志仍可用。

被否决的首版候选 f6b526671 使用真实配置供应商、合成临时账号、executor/Pi/Gateway 的两次实际 API 回放均报告 complete：新会话 11502 ms，前轮失败会话 5341 ms；分别两次/一次模型调用，只开放通用知识，零个人工具执行、零写回执，保存与流逐字一致。3 次供应商 usage 均 API 实报且成功。仅证明这两个合成请求，不是生产账号、手机体验或临床质量验证；模型自然语言仍有随机性，不承诺固定速度或穷尽所有问法。脱敏摘要见 `docs/reviews/2026-10-14-daily-planning-question-verification.json`。


## G4 NO-GO 与修正

首版 f6b526671 未推送或部署。独立 reviewer 判定 NO-GO：虽然工具流程完成，实际模型输出仍凭钟点判断不适合剧烈运动，并建议固定就寝时间；仅加强 prompt 不能证明输出质量。两次真实 API 成功不能当作修复验收。首次质量输出文件不完整，纠正原“已保留”表述。发布包装脚本独立 GO 不覆盖被否决代码。

最终实现复用已有的 current_input_local_advice 持久化、幂等重放与源消息绑定路径。完整日常安排请求只按闭合期限及领域枚举选取受审文字，运动注明自身能力、医嘱、不适和就医边界；饮食保留过敏/饮食要求，不生成减重或摄入目标；睡眠按困意及原有作息，不输出固定量或钟点。明确无个人记录查询、无计划保存，未将用户背景或模型推断放进答案。仅保存对话，健康数据不变；DB 保存失败不能发出成功终态。

新增无模型/上下文/工具调用的真实公开入口测试先 20 failed，再修复；覆盖两种客户端 panel 选择、原句和语序/空格变体、持久化与重复请求逐字重放。补充准确原句的其他账号会话拒绝、持久化故障和源附件恢复边界。原模型候选的 5–12 秒结果不属于最终版本性能证据；最终版本不调用模型，本机/PostgreSQL 与线上检查分别记账。

最终本地候选：关联回归 304 passed；一次性 PostgreSQL 84 passed / 93.93s，stop exit 0。离线 LLM invariant/trajectory 闸、System Map、Dossier 与 diff 检查通过。尚待新固定提交的独立复审、完整 CI、发布与线上验收；首版的包装脚本 GO 不替代新 SHA 复审。

## 主干集成与发布归属断点

推送前 fetch 发现 main 已由另一任务更新为 b5110ff144dc840732fa8458dc336a221fb5f787（LifeNav UI；精确 CI 38572169088 success）。在推送前的显式相等检查停止，未执行 push、授权轮换、部署或 OTA。按 AGENTS 第 7 节已向用户询问发布归属；未以无 lease 推断另一任务已经放弃发布。

本地无冲突合并产生 fcc323c3159f94bc48b95cc48f240ad2aedf96b2。Agent 文件与已审 3f62 逐字一致，LifeNav 9 个文件与远端 b511 逐字一致，其他 dirty 文件保持原样。整合后 Mobile 33 tests、TypeScript exit0、System Map 和 Dossier 闸通过；独立集成复审 code/wrappers GO，仍显式要求 ownership 澄清后才能外部写入。最终精确候选的本地 CI-mode 闸在执行；前两次因候选被否决/替换的本地闸主动中止且保留原结果，不能计为通过。发布后真账号/手机端验收尚未发生。

最终集成 SHA 的 clean CI-mode 发布不变量闸通过：3774 passed、22 skipped、84 subtests passed / 547.17s，真实 exit0。仍未 push，故精确主干 CI、生产部署、OTA 和手机验收未发生。唯一当前交接阻断为发布归属待用户澄清；既有本地修复及完整证据可继续沿同一 trace 交付。

## 用户授权后的统一发布

用户明确回复“ 一起发布 ”，发布归属解除；精确候选 fcc323c3159f94bc48b95cc48f240ad2aedf96b2 已正常推送 main，远端完整 CI 38578258596 开始执行。生产只读复核发现 LifeNav b5110ff 已先完成 backend 38574797238 与 OTA publish 38576013830，生产 SUCCEEDED、无业务租约或运行态事务。旧 e9ca 前序绑定不可继续执行；四份包装脚本仅将前序 SHA 改为 b511，并提交独立安全复审。

Mobile 与 shared 树分别为 60e59ed75ba566dcb741c983497d87a1f3d19ea2、4bfc7001affb763d9fa08dced80111a92aec83d9，候选与已发布 b511 完全一致。已回读 production iOS runtime1.3.5 的 OTA durable intent/verified/completed 摘要一致，update 01a13ab6-5f2b-7fb8-9ab2-42edd1d5964e；不将旧 SHA OTA 冒充 fcc OTA，也不重复发布内容相同的空 OTA。待本次后端成功后，以同树复用说明汇报两端实际发布状态。

精确 main CI 38578258596 全部 32 项检查成功；trusted-release validate 38580047831 成功。重绑定 b511 前序的独立安全复核 code/wrappers GO（/tmp/reva-daily-question-unified-g4.json）。服务器匿名 GitHub API 余量 20，低于整套轮换所需额度；等待 reset 后才允许 stage/revoke，不降低阈值或提前撤销旧授权。

等待额度期间主干新增 93725987775cbe6c9e11cb24f48779049acc319f（仅 LifeNav Web CSS 与验收文档）。按用户一起发布指令将本地 main fast-forward，无源码冲突，Agent/backend/Mobile/shared 均未改；新候选重跑 clean CI-mode，等待远端 CI38580123045，并仅替换包装脚本候选 SHA 后独立复核。此前 fcc 的 CI/validate 仅归档作旧候选证据。网页发布仍受现有无备份冻结入口约束，本次不调用 Web publisher，也不把后端部署称为网页上线。

937 的本地 CI-mode 3774 passed/22 skipped/84 subtests 与 remote CI32项、validate38582489426 均通过后，生产只读最后检查在 current-main 相等断言失败，未执行 staging、撤权或轮换。主干由 ad2645dd0、1f061b942 更新恢复建议语法及开场白，涉及同一 scope 文件，不能归为纯文档。已再次请求暂停其他推送并明确统一归属；外部写入暂停，本地 fast-forward 到1f061b942 并继续独立集成复核及全新 CI-mode。现有生产 b511 和原锁/授权未由本会话改动。

用户在处理新增附件会话明确回复“合并到main 跟其他发布一起发 包括ota”；已通过 read_thread 核验原始用户消息。该会话交接566f7c5fa并停止继续 commit/push/deploy/rotate/OTA，本会话统一发布。新候选包含饮食页返回主Agent及单日读取修复，需新的OTA，旧同树免OTA结论不再适用。重新绑定最终G4和全新CI-mode；不带入其他dirty文件。

## 最终整合畸形查询参数修复

566f7c5fa 的独立复核发现新饮食 batch 中 dimension 为列表或对象会在 scope 集合判断抛 TypeError，真实 Gateway 转为 ToolPreflightError，零 dispatch；代码 NO-GO，未推送或部署。新增 210 个单项/batch/plan、五个维度别名、enforce/shadow 的公共 Gateway 回归先失败，另5个合法别名通过。修复在维度归一化与 scope 匹配之前拒绝任何已提供的非字符串维度或别名，使用已有强制阻断 reason，不将异常值字符串化；未提供的字段及合法别名保持既有语义。修复后整合相关测试608通过，相邻能力、Gateway、维度归一化与Garmin状态5818 tests通过；无新schema、权限或写路径。System Map/Dossier、秘密扫描与LLM change gate通过（live_llm_required=false）。后续使用新固定提交复审、精确完整CI和CI-mode，旧候选证据不代替。

远端 d586 CI 的 balanced-08 发现旧测试仍预期忽略模型传入其他owner后继续读取；本次566安全语义已明确拒绝模型身份字段，因此更新过时allow预期，不回退账号隔离。新增single/batch × user_id/owner_id/tenant_id × enforce/shadow的公共Gateway零dispatch测试。相关回归319 passed/12既有skipped；新owner测试单独13 passed，无跳过。此收口仅修改测试和文档，生产runtime与已独立GO的d586字节一致；仍需新候选精确完整CI。

同轮CI balanced-12的晚间总结两例也沿用丢弃外部owner后allow的旧预期；将本人正常查询与外部owner拒绝拆开覆盖，保留原日期投影正例。三组相关测试351 passed/12既有skipped。此后续仍仅测试和文档，runtime未改；统一保留失败日志，不把旧红色CI计为通过。
