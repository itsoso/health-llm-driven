# 饮食卡片底部操作与恢复陈述修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 安全复审通过；G5 精确 CI 待完成 |

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
