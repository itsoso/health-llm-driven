# 饮食卡片底部操作与恢复陈述修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | da91 后端已部署；OTA claim 失败，回 G3 补安全关闭与发布准入 |

## G1 需求与范围

裁决：PASS。修复现有餐卡布局与本人恢复记录表达，不新增健康决策或数据对象。

用户提供两张截图：饮食卡片的查看/修正按钮打断营养信息阅读；“感冒好了”误走未授权历史查询。按既有行为修复，未新增健康建议、诊断、数据库结构或接口。

- 已记录卡片：照片、热量、食物、营养、建议、估算脚注保持连续；查看与修正组成底部操作区，窄屏可换行，最小高度48。修正编辑器在操作区后展开；未保存草稿确认流程保留。
- 完整、确定的恢复陈述（包含省略“我”的“感冒好了”）走既有本人病程更新路径。全句匹配与精确疾病实体解析继续拒绝引用、他人、否定、条件、部分恢复、问题和额外动作。
- 仅从当前认证用户的已读取病程中更新唯一 active/improving 同名记录；零条、多条、他人和已结束历史记录不能被猜测覆盖；持久化与回答回执必须一致。

## 实现与证据

Router incident + safety，Health Harness控制；未加载已禁用superpowers。UI与后端有独立文件所有权，保留之前benchmark及发布证据WIP。

- UI排序先RED（1 fail/7 pass），再两个相关suite 110 PASS，tsc通过。
- 恢复陈述新增5条原失败表达先RED（5 fail/4 pass）；修复仅拓展既有闭合句式的本人省略与“好了”，77个本地回归通过。
- scope/capability/classifier/symptom相邻测试3437 PASS。
- PostgreSQL隔离库初次因initdb默认SQL_ASCII无法编码中文失败（49 pass/28 errors），未操作业务数据库；改为UTF8重跑77 PASS/61.77秒，pytest与隔离库停止均exit0。
- LLM change gate PASS、live_llm_required=false；map/diff通过。无真实模型评测、无备份。

- 独立审查固定提交8a50a04发现中间问号被疾病名称清洗吞掉的授权边界，裁定NO-GO；新增4条疑问反例先RED，再于实体解析前拒绝原句问号，SQLite全套81 PASS。修复提交需重新独立审查。

## 当前状态

实际DietDraftCardView经React Native Web渲染320/390/768px截图目视通过，均无水平溢出；320两钮各258×48上下排列，390各160×48并排，768各349×48并排。证据 `/tmp/reva-diet-footer-preview/`，合成无照片餐食、仅路由/隐藏编辑器/平台桥接stub；这是浏览器预览，非原生验收。

a17884a8c固定提交独立安全复审GO；最终PostgreSQL81 PASS、相邻3437 PASS。首次CI38400854262因本Dossier缺状态表及G1准入段失败，已补齐，需新候选完整CI。本轮尚未发布。模拟器/真机实际UI与拍照时延未验。

## 发布回执追加

最终ba53273c01f04af20958e364fa255a648947857e：独立安全复审GO、正常成功版授权轮换包装器GO。完整CI38401354358全部32项通过；同SHA文档push CI38401353204及trusted validate38403191359通过。旧a178候选CI原文档失败保留，后续取消其剩余任务释放资源；未取消最终SHA的运行。

后端38404091257成功，root SUCCEEDED、runtime COMMITTED、生产HEAD相同，backend/worker/beat均active，公开健康接口healthy，发布lease不存在。实际deploy阶段266秒。线上纯解析合成3正例/6反例通过，零模型调用、零数据库写入；不冒充真实账号端到端验收。

原生1.3.5(288)精确源构建并发布，支持iPad，签名仅1个已登记设备；5项上传摘要及公开IPA读回一致，latest别名未改。安装页与完整证据见 `docs/reviews/2026-10-13-diet-footer-recovery-release-receipt.json`。未发OTA（既有native baseline不兼容），未发TestFlight。未做真实模型评测、真实相机/设备验收或拍照时延验收；无备份。此追加证据保留本地，避免改变已发布SHA。

## TestFlight 与 OTA 续发授权

用户在后端与直接安装包发布后明确要求“发Testflight和OTA”。TestFlight使用独立纯交付文档提交及trusted-release target=testflight，保持已部署运行树不变，不重复后端部署、不复用288 ad-hoc包冒充STORE。OTA先检查固定原生baseline、production cohort fingerprint和精确SHA后端条件；未通过时不领取publish claim。新原生构建完成并不自动更新baseline，不将TestFlight上传、Apple processing与测试可用混为一谈。沿用不备份、不真实模型评测及模拟器默认验收要求。

## 恢复确认截图续修

用户继续提供“感冒确认痊愈今天”截图：前文病程名称是“感冒样不适”，当前句式与三层精确名称授权均未衔接。新增3种明确确认表达先RED 3 FAIL/9 PASS；恢复分支仅以闭合原句解析目标，在本人本轮列表中同时考虑“感冒”和固定“感冒样不适”标签，必须唯一active/improving，不按子串或历史助手文字猜ID，不改病程名称。明确今天/今日从执行上下文用户日期构造end_date；只允许status及同日字段，模型缺日期时补同日，其他日期或额外字段拒绝。未来或非法起病日期不自动恢复。

起病日期边界先RED 1 FAIL；修复后恢复145项与相邻3437项共3582 PASS，CI=true隔离合成环境。首次新增单测fixture误用了ActionableReference.source导致11项TypeError，修正后重跑，不作为产品RED。PostgreSQL145项正在运行；map、secret scan和LLM change gate通过，真实模型不要求亦未执行。

原d461纯文档续发候选完整CI已取消且未开始授权/构建/上传；本次新后端变更将按新精确SHA完整CI与独立G4后使用target=release，让后端部署与TestFlight构建走既有流程。OTA仍单独核对原生基线，不因新包构建成功而跳闸。

固定dfdd提交独立G4裁定NO-GO：实际列表证据生产器遗漏start_date，绕过未来起病检查；日期归一化与授权归一化不一致，空格/尾部标点可丢失明确今天。新增实际GET→更新网关反例与日期归一化/缺失日期反例先RED（4 FAIL/3 PASS），修复只在illness列表证据保留start_date，恢复分支要求合法且不晚于用户当天的起病日期；今天解析复用normalize_write_scope_text。修复后3589 PASS，System Map检查通过。原PG145 PASS但停止进程返回非零，已确认没有遗留该测试PostgreSQL进程；新增152项隔离PG正在重跑，不把旧结果代替新结果。

agent_executor变更触发真实模型评测门槛；沿用用户明确“后续不需要真实评测”，对最终精确SHA设置waiver，绝不伪造confirmed。新候选仍须独立G4、完整CI、部署与原生/OTA实际回执后才能声明交付。

## 加餐短句与账户时区续修

G1 PASS：截图“加餐一小个桃子”被误当只读请求，并出现计划草稿失败；同页23:06显示15:06。沿用当前Dossier与Health Harness，incident+safety，不运行真实模型评测或备份。

- 完整餐次+份量+已知食物名的当前本人陈述进入既有饮食记录目标；拒绝未来、他人、否定、疑问、引用、药物及复合动作。不放宽网关用户隔离或回执要求。通用失败文案不再误称计划草稿。
- 会话历史API将UTC存储值序列化为明确+00:00；Mobile兼容旧无偏移UTC，按账户effectiveTimezone显示消息、日界、历史及分享图日期。时区查询按用户隔离并响应设置失效，未取得有效时区时不冒充设备时间。
- RED：加餐4 FAIL/14 PASS；时间API1 FAIL；Mobile7 FAIL/4 PASS。GREEN：后端相邻1780 PASS，历史API60 PASS；Mobile104 PASS、tsc PASS；System Map及秘密扫描PASS。完整鉴权API写入、持久回执、同client_turn_id去重纳入回归。
- 隔离PostgreSQL验证进行中；固定提交独立G4及发布尚未完成。当前生产仍为0fd447cbd；既有OTA原生基线不兼容阻断继续保留。

固定实现提交531556db53edbeedbd05ded551c585d63398db4c独立G4 GO：reviewer独立81项后端、104项Mobile及19项额外负例通过。隔离PostgreSQL63 PASS/71.21秒，测试与关闭进程均exit0；本地LLM gate按该精确SHA用户要求waived、confirmed=false。报告/tmp/reva-snack-time-safety.json。当前仅本地修复与验证完成，未push、未部署、未发布OTA/TestFlight，未做原生视觉验收；不得将上一候选发布回执用于本次改动。

## 2026-10-14 直接痊愈陈述的隐含当天日期续修

用户再次提供“我的感冒已经痊愈了。”被拒截图并要求修复发布。可复现分支：闭合本人当前痊愈语法此前仅在显式今天时构造end_date，模型传正确同日日期也被精确patch检查拒绝；status-only依赖API服务器日期或已有日期。未读取截图对应生产工具参数，不把此分支宣称为唯一根因。

本轮仅修改capability_policy.py及test_illness_recovery_turn.py：直接当前痊愈语句由系统绑定context.current_time用户本地日，接受status-only或完全一致的同日patch。仍要求本人列表唯一active/improving、精确候选ID、合法且不晚于当天的起病日；模型历史日期、附加字段和错ID继续拒绝，不读取历史助手文字作为授权，不修改服药记录。

证据：新增固定UTC/上海跨日用例先RED 2 FAIL；扩展截图原句的run_stream→鉴权API→真实数据库→持久回执链路，SQLite181 PASS，相邻授权2501 PASS，隔离PostgreSQL181 PASS（133.17秒）。模型使用scripted provider，未做真实模型或真实账号验收。独立安全文件预审GO，尚非固定SHA G4。System Map、任务文件秘密扫描、diff检查通过；LLM change gate报告live_llm_required=false、confirmed=false。最后将全链路测试日期断言改为账户时区以避免UTC CI时间窗口差异，正在重新验证。

日期断言调整后SQLite181重新PASS（31.94秒）。PG测试已通过，但第一次pg_ctl fast关闭等候超时（检查点未结束），正在仅对本轮隔离测试cluster延长等待；不把测试结果与清理结果混同。

发布仍统一交由“优化 README”线程；本线程未stage/commit/push/deploy/OTA。待最终固定SHA独立审查、完整CI及发布回执后补交付结论；不复用旧候选回执，不重试既有失败OTA。

隔离PG清理已由接手会话独立复核：2026-10-14 09:52:44（Asia/Shanghai）server.log明确database system is shut down；对实际数据目录/tmp/reva-recovery-pg.U5Tk0G执行pg_ctl status确认no server running，postmaster.pid不存在。首次fast等待超时是144.59秒检查点超过默认等待，不改变181项测试PASS，也不虚报首次关闭命令成功。固定SHA G4、完整CI及本次新修复发布仍待完成。


## 2026-10-14 痊愈来源标签与餐卡营养同步续修

G1 PASS：截图病程实际标签为“感冒样不适（用户自述）”；此前已部署72b4a09a修复本地日期，但固定名称集合没有此来源后缀。新截图还显示已保存餐卡热量缺失且后续未更新。本轮修复既有记录选择与投影，不新增诊疗决策或数据结构。

- 只增加精确“用户自述”括号来源后缀的名称等价，非任意括号剥离；他人、待核实、复合疾病限定继续拒绝。截图原句、唯一本人病程、日期和重复候选边界均回归。先RED3FAIL，SQLite285PASS、相邻授权4446PASS、隔离PostgreSQL285PASS，测试及停库exit0。
- 已保存餐卡的历史交付从本人真实DietRecord批量刷新营养、食物、日期、版本及未降精度的编辑基线；照片parent转换后再刷新。删除/不存在/跨owner返回不可用状态，不展示旧营养或动作。先真实合成PUT→历史卡RED，SQLite76PASS、PostgreSQL76PASS，两项退出均0。
- Mobile按同owner、同record_id及更高updated_at同步后续轮和历史餐卡；明确null初始版本可被第一次真实更新替换，未知版本不可猜。后台PUT/重估成功结果发进程内通知，账号代际与当前身份复验后更新现有餐卡，不增加识别、轮询或重复显示；缺失营养保持null。事件链先RED，相关7套188PASS，补跨账号测试后事件/聊天144PASS，TypeScript通过。
- Live自动保存producer补user_id和数据库版本；health_manage成功PUT只有在结构化写回执、owner/ID、版本及完整返回字段验证后才产已保存餐卡。只使用API返回行，不使用模型文字或请求估算；完整执行链已在隔离PostgreSQL验证：14PASS（其中1项run_stream→真实网关→鉴权PUT→DB→回执→done餐卡→AgentMessage.meta），单次成功写入900→450，fiber保持null；测试及停库exit0。相邻执行/照片/历史卡311PASS、1既有skip。
- OTA原生阻断已取得实际EAS276/277指纹来源证据：287项中285项一致，唯eas.json与方向插件源码不同；精确Git摘要匹配，production配置相同且supportsTablet=false，插件12组输入24次输出一致。仅为固定双构建cohort及精确原生源摘要例外，不对未知差异放行；先4RED，264PASS/1既有skip。独立固定SHA审核尚未完成。

当前为G3完成/补验阶段，未发布这些新改动。后续须固定提交独立G4、精确SHA完整CI、后端部署与trusted OTA validate/publish真实回执。沿用用户不备份、不真实模型评测要求；agent_executor变更使用最终精确SHA豁免，不伪造confirmed。不以合成测试冒充真实账号、相机、设备或线上时延验收。

最终补测：Mobile旧餐卡同步保留服务端编辑种子的原始营养精度，先RED后12PASS；全程无额外模型调用。System Map、TypeScript、秘密扫描及diff检查通过。

## da91b5de 后端交付与 OTA 领取阶段失败

固定 da91b5de303313f1fb014bbe045e8f1597d15229 独立 G4 GO，完整 CI 38506475019 全部32项通过。trusted validate 38507720283 与 backend 38508552627 成功；实际生产 HEAD、root SUCCEEDED、runtime COMMITTED 一致，backend/worker/beat active，公开健康接口 API/数据库/Redis/Celery healthy。线上部署代码12项纯合成检查 PASS，未访问业务数据库或模型，不代替真实账号验收。

OTA validate 38509087278 返回 PREPARATION_PASSED。publish 38509318595 attempt1 在 claim-ota 阶段 command_failed，未进入受审 publisher 的 vendor-publish 调用。官方 artifact 11869725525 的 ZIP SHA256 为 dba9fdf15b0098e982627210ea67f29a146d038729ccc2e405fb6230beb2050a，与下载字节一致；仅有 ota-diagnostic.json、ota-claim.json、ota-preflight.json。生产原 OTA 目录保留 intent.json 与 lease.json，未生成 claimed.json，业务租约仍保留。没有重发、删除锁或伪造成功回执。

只读复测 canonical backend proof 在 trusted_testflight_preflight.py 的 gate.verify_release HTTP 请求处失败；同刻生产 GitHub 匿名额度0/60，重置时间2026-10-14 04:43:40 UTC。这是当前诊断证据，不能单凭复测断言原失败唯一原因。现有 recover 只支持已有 claimed 和 vendor receipt 的同回执收尾，不能用于本次部分 claim。下一阶段在同一 Harness 中补受审的未发布 claim 失败关闭与消费前额度检查；旧操作必须以明确失败终态保留，不能改称 OTA 成功或复用原 SHA 再发布。

发布准入补修：claim-ota 的完整精确 CI 移至 intent/lease 之前，取消同一入口外层重复核验；同一生产 SHA 不再重复_latest。额度不足在消费前拒绝，原双锁、本地源码/成功回执/服务/租约复核保留。证明只在进程内单用，前后核验有效期，不新增CLI绕过参数。现有线上只读阶段实测 revision 46.58秒、历史reset审计73.29秒、frontend审计0.09秒，关键链约119.96秒，因此有效期采用240秒而非未经测量的120秒；这是发布证明耗时，不是拍照识别耗时。177项离线相关回归通过；新未发布操作关闭器仍待完整验证与固定候选独立G4。

补修整体验证：关闭器47项纯合成专项测试，发布准入/历史 adapter177项通过；合并运行八套发布相关 CI-mode 测试647 PASS，System Map和文档漂移检查通过。关闭器只接受固定失败workflow/attempt/job和官方artifact ZIP及三项内容摘要，保留原两文件及租约身份；执行前后健康/进程/双锁复核，失败终态与成功发布分离。真实下载证据通过纯验证器校验；尚未执行生产关闭。待固定提交G4、完整CI后按inspect摘要执行一次；无重复OTA或备份。
