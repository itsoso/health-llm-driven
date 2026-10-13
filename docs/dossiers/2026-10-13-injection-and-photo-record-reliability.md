# 注射记录与拍照记餐修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 产品安全 GO；G5/G6 发布前置条件未满足 |

Primary controller：health-harness-orchestrator；overlay：safety-gate。superpowers禁用。用户明确要求解决注射照片记录、食物无法识别时的错误与拍照记餐性能；真实模型评测继续按用户要求不执行。保留原三个benchmark脏文件与其他历史未跟踪回执，不修改或暂存。

## G1 范围

裁决：PASS。复用现有用药日志、餐食草稿、手动确认与聊天附件；不新增医疗决策或自动处方行为。

截图“重新开始注射替尔泊肽”加药盒照片被转成未授权个人读取；该句话不证明已经注射，也没有实际剂量。另一个记餐截图显示等待确认，处理详情却显示未完成，并且首卡延迟到正文/终态之后。修复已有记录与确认闭环，不新增处方、提醒、自动恢复用药或新健康对象。

## G2 边界

- 注射caption仅支持有限全句、已知替尔泊肽别名。重新开始/恢复只追问是否已注射、实际剂量与时间；包装图片不作为实际剂量。明确刚刚/刚才已注射并提供实际mg或已注射针/支数时，复用owner/source/hash/TTL绑定的manual-confirm用药计划。确认后才保存一条MedicationLog，基础Medication不设置处方频次或提醒。照片沿用聊天附件保存。
- 带图消息仅允许服务端已保存图片列表对应的确切附图计数后缀；完整原消息仍参与计划hash。改caption、药量、计数、缺图或跨owner不得放宽；普通口服解析的数量与包装规格区分保持不变。
- waiting_for_user在处理详情显示等待确认/补充，过程保持中性，不宣称处理失败或已完成。真实error/interrupted优先，不被过期waiting状态遮盖。
- 对低置信度餐食，先核验当前owner/source下已经持久化且未过期的pending draft，再流出确认卡；没有write_verified里程碑或写回执。正文改为初步识别仍需核对，照片与草稿保留。
- 最多3张图仍先去重；最多2个视觉读取并发，校准、聚合、捕获和数据库操作都在父任务按原图次序执行。TaskGroup失败或取消关闭同批异步兄弟任务，不执行capture；不承诺已经提交的上游同步SDK网络请求可撤销。模型、prompt、图片参数、数量限制和确认阈值不变。
- 明确记餐的结构化识别异常产生可见失败与原图绑定，不再触发额外普通Vision请求；非餐食的通用图片仍走原处理路径。没有识别到食物为等待补充，真正服务故障仍是可重试失败，不伪装成功。

## 性能基线与验收

当日已有自然阶段聚合5个provider返回，中位2497ms、样本P95 7632ms、P99 8247ms；解析阶段中位0ms。它们不是配对端到端请求，返回也不证明识别/保存成功。用户截图图像阶段4.7秒、本轮4.9秒仅为单次用户证据。当前默认目标为通常3–5秒可核对首卡、较慢8秒；尚未取得该目标的真实生产P95验收，不以合成测试承诺手机实测达标。

原1841源码方法与当前方法同批8组、每组3张合成provider耗时配对，中位78.59→52.73ms；各组数据/输出完全一致、provider调用数相同，峰值并发1→2。只证明受控调度与输出等价，无真实模型、数据库capture或生产时延证明。单图上游模型等待不会因此下降。

## G3 当前证据

实际PostgreSQL原注射stream RED2 FAIL；修后两个照片追问/提案→确认→重放流程PASS，日志/tmp/reva-injection-probe2.log，runner0/PG正常退出。首次宽域包含新增测试自身未导入parser与误用WriteIntent.conversation_id的错误，保留失败；修正为payload中的conversation_id，没有把测试错误当产品修复。

处理详情UI RED1 FAIL/9 PASS；修后相关UI61 PASS。pending首卡实际PostgreSQL RED1 FAIL，追加recorded=false与owner/source/token校验后PASS。并发合成RED1 FAIL，修后重叠/顺序/去重/取消和失败关闭测试通过。第一轮宽域323项尚须最终终态与新源重跑：已知旧文案期望1FAIL，已改为核对不确定性的精确文案，不能沿用其旧候选结果作为最终绿色。

## 发布约束

G4须固定最终来源做全新独立安全审查，精确主干完整CI与项目CI-mode均须通过。不得真实模型评测。用户2026-10-13禁止后续备份及普通发布全量核对历史备份；当前生产发布器仍有env/运行态回退副本和历史核验入口，必须先适配，不能重放旧wrapper或静默绕过原回执/锁/健康门。当前尚未部署，Mobile等待状态变化尚未发布；OTA/native边界须重新核对，不能借旧native基线强行OTA。

### G3 追加边界与固定候选准备

第一轮323项宽域实际1 FAIL/322 PASS，失败为旧肯定文案期望；修订后的326项PG全部PASS，pytest与runner0、PG正常关闭。后续44项实际边界PG PASS，验证首卡owner/source/未过期/只读/写入暂停条件、注射保护状态、原确认卡保留、没有新写入及恢复后通过原卡对应计划确认。只读卡片额外RED1与暂停提案RED1均真实复现并收紧。首个卡片边界fixture因高置信度自动保存导致非draft，不作为产品RED；明确低置信度后复现readonly问题。

保留原立即相邻两回合的聊天确认规则，没有为了保护状态后的泛化“确认”跳过其他消息；服务恢复后可从原绑定卡片手动确认原计划。新用量mg/针在模型提议及最终payload校验两处都必须与显式source caption一致，包装规格和改剂量都拒绝。source原文连附图标记完整hash绑定。

补充明确刚刚/刚才打针、中文数词与mg/针/支记录，不从针数折算药物质量；0用量只追问，不保存。此次最终来源待固定；最终完整PostgreSQL/全Mobile/独立G4/当前精确CI尚未完成。


### G4 首轮 NO-GO 与整改

固定候选 `5b45fdcf3b015804391de6aa815e5a6715ad11f6` 独立审查 NO-GO。PG 373 PASS + 独立注射源绑定 4 FAIL；食品 capture / 实际 run_stream 的 readonly、runtime 暂停边界分别 4 FAIL，Mobile 174 PASS，全部正常停库。报告 `/tmp/reva-injection-photo-fixed-safety.json`。这些是生产者路径真实缺陷，不能用首卡隐藏掩盖。

整改将替尔泊肽所有单位与明确原消息绑定，同时拒绝模型添加包装规格；提案前和确认最终 payload 两处同样验证，哈希正确也不能绕过实际量事实。食品实际捕获入口阻断只读/暂停下的 DietRecord 与 DietPhotoDraft，并阻止将识别快照保存为后续修正依据。

补充多图营养标签缺实际食用重量时标记不完整，不能把另一张成功结果当完整餐食自动保存；仅需补食用量的图片回到等待补充。首轮新增11例 RED 包含10个真实边界失败和1个测试无效图片路径；修正该 fixture 使用真实本地上传后，专项39 PASS，63.08秒，pytest/runner0，PG正常退出。原无效路径失败没有作为部分记餐产品RED；另加载固定5b45方法复现多图标签原行为，结果另记。

最终完整PG、全Mobile、当前固定候选重审尚在推进。工作流 trace `docs/_generated/harness-runs/6a4c749f489b.jsonl` 绑定本Dossier，首轮NO-GO已记录；使用一次 trace，不另建安全ledger。


### G4 第二轮 NO-GO 与全剂型事实绑定

固定 `02a93ad0320edb6afc87ffd98e367ac8105e42c5` 独立 reviewer 发现 owner 已有“替尔泊肽注射液”名称时可用错误2支绕过source1支，真实manual confirm产生MedicationLog。独立PG确认1 FAIL，正常停库；此前注射4例、食品实际stream4例整改均独立PASS。报告 `/tmp/reva-injection-food-final-safety.json`；归档环境缺Pi依赖造成的宽域失败单列，不覆盖此真实阻断。

新增精确全剂型别名，不做substring folding；明确注射caption下，模型不能以其他owner登记自由药名替换药物或量。restart只允许追问，不允许生成另一药名的用药提案。新增4个全名/确认/解析实际RED和2个自由名称实际RED，pytest/runner均1、PG正常停库；整改后的132项用药与别名回归正在运行。

修正图片fixture后，加载固定5b45原方法独立实际复现多图营养标签缺份量时错误自动保存（DietRecord=1），1 FAIL；当前39专项中的对应完整性用例已PASS。该基线加载仅使用旧方法+同一输入，不访问真实模型。

全Mobile 347套、3549 PASS、1 skip，112.269秒；TypeScript无错误、System Map和Skill治理通过。离线LLM gate通过，真实模型gate仅按用户既有豁免绑定02a完整SHA，confirmed=false，不宣称真实评测。完整发布不变量CI-mode在02a固定Git来源运行，后续药名改动未由其结果证明。


### 最新验证终态

食品、草稿、用药与turn outcome宽域在02a来源运行391 PASS，669.21秒，pytest/runner0，PG正常fast关闭；后续源码变动仅为用药精确别名/source药物绑定，对应132项新用药/别名PG全部PASS，319.24秒，正常关闭仍待runner终态读回。新增全剂型带图提案→确认→重放正向stream正在独立定向运行。

02a的本地发布不变量CI-mode因该候选已被第二轮G4拒绝而发SIGINT正常停止，退出2，554.87秒，原结果保留`/tmp/reva-report-performance-final-ci-result.json`；没有将其作为通过，没有取消GitHub CI、生产发布或消费任何新claim。最终候选发布CI-mode仍未通过，发布准入保持BLOCK。


### G4 最终 GO

产品固定候选 `e64aa3d6a06dbf0985f2e10251e028fa6915d0be` 新独立 reviewer GO，报告 `/tmp/reva-injection-food-gate3-safety.json`。PG独立20+2 PASS，两个pytest/runner0且正常停库；Mobile消费链10 PASS。审查首轮因临时DB名字不含test触发fixture保护的20个环境ERROR保留，修正审查runner重跑，不改产品代码，不当作产品RED。

已验证source药名/实际量/包装强度、正确hash篡改payload确认拒绝、owner已有全剂型Medication正确确认重放、只读/暂停实际stream不创建餐食或草稿、pending首卡不声称write_verified、no-food与provider真实故障区别。父端132项PG与带图确认2项runner最终均0，正常停库；食品宽域391 PASS、Mobile3549 PASS/1skip、类型与地图/Skill治理均通过。没有执行真实模型评测或生产健康写入。

发布准备仍BLOCK：无备份生产者/消费者尚未适配；最终发布CI-mode未通过；目标main精确完整CI待推送核对。因此当前修复不能声明已部署、已OTA、已TestFlight或真实手机拍照耗时已达标。最后新增文档仅同步终态证据，产品源码不再改变。


### 精确 main CI 治理失败与修复

`3640b8041a25856e84a7df96be90cbaed60ae955` 已推送main，CI `38345357344` 的balanced-11实际失败：`test_agents_contract_is_concise_and_does_not_embed_a_skill_catalog`，AGENTS 10872字节超出10KiB；该分片839 PASS、10skip，仅此1 FAIL。其他分片仍以真实终态为准。失败源于先前追加无备份要求后的入口体积，并非注射/餐食行为回归；不取消该CI，不重发同一失败source。

本地首次普通pytest因缺少默认本地PG而在fixture前失败，未进入治理测试；保留原日志。纯工具AST守卫单项随后实际复现1 FAIL，压缩后1 PASS；首次全补充入口也在旧AGENTS上1 FAIL/177 PASS，保留失败。当前仅精简AGENTS叙事，将已有兼容字段语义引用到原治理规范，并将专用隔离测试命令移入测试规范；不删除备份禁止、锁/回执/CI/健康闸、安全或模拟器未验证边界，不修改10KiB断言。首版压缩入口10230字节，完整补充治理检查正在终态读回，产品代码blob仍不变。

下一候选是治理文档修复，不可仅使用纯文档轻量绿色冒充完整发布CI；按既有恢复规则在新main精确SHA补一次完整CI。无备份发布链前置BLOCK仍保留，不调用旧发布脚本。


治理首版全补充检查额外发现fast lane契约要求隔离命令必须直接出现在AGENTS（1 FAIL/177 PASS）；已恢复完整命令及适用范围、默认入口和coverage约束，未改测试断言。最新AGENTS为10201字节（<=10KiB），完整纯工具补充入口178 PASS，8.32秒，进程0；Skill治理检查PASS。产品源码没有变化，此补充验证不替代新候选完整CI。旧main CI终态仍保留失败。
