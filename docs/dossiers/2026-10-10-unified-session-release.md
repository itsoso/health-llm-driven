# 跨 session 统一整合与发布

| 字段 | 值 |
| --- | --- |
| 状态 | blocked |
| 当前阶段 | 最终637520e25完整CI全绿；后端被既有Runtime熔断硬闸拒绝并回滚，G5/G6 BLOCK；Web/OTA未发布 |

## G1 范围准入

裁决：PASS。用户明确授权实现后整合其他 session 并完成最终部署和发布。本次汇总既有个人周导航、健康只读导航、运行分析、每日建议 TokenPlan、仪表盘和环境展示、Workout 图表、照片份量回执与可信 OTA 目录修复，不扩大健康写权限或原生包发布范围。

## 固定来源与整合

个人周导航 e7ad64513、忙碌状态 6adc1de1b；Web/TokenPlan 汇总 c4c05120b；照片回执 5ccf5b9a6；远端主干和可信 OTA 修复由 8ba1df80b 正常合并；文档及地图 e1dac0239；CI 测试目录 19f748b13；跨账号缓存隔离 4952ee90c。原本未纳入的视觉验收文档保存在 Git stash，未覆盖或删除。其他 session 已交接并停止独立发布。

## G2 与 G3 本地证据

原功能规格及各 dossier 继续作为行为范围真源。统一数据库 CI-mode：349 passed、5 PostgreSQL 专项 skips；独立 PostgreSQL17 实际整合：283 passed；Mobile 全量：3370 passed、1 skip，TypeScript 通过；发布工具：219 passed、4 macOS 不适用 skips；Web 最终全量：513 passed、1 skip，TypeScript、lint 通过（既有 39 条 lint warnings 保留）。OpenAPI 双端生成类型检查、System Map 和 dossier consistency 通过。运行分析及导航新增模块已纳入正式 CI 选择器。

本地 Next 安装版本与锁文件不同，锁依赖完整验证以本次精确 SHA 的 GitHub CI 为准。独立审查发现旧账号创建、换号后发送的缓存污染，已补真实页面闭包与请求层失败回归后修复。独立 lifenav_readiness 对固定实现 SHA 4952ee90c 复核安全 GO，原缓存阻断解除；本记录仅补交付证据，不改变实现。

## G4 发布前闸

安全 GO；最终候选 b5e96ee84236b7ecdcd2de4914fbe6e2d13b432b 的完整 CI 37974764859 全部 30 jobs 成功。不得以本地检查替代。所有外接 LifeNav 开关继续关闭；没有接收方真实联调或七天使用证据。

## G5 与 G6 发布和现场验证

G5：PASS。后端可信发布、Web 独立发布和 iOS 可信 OTA 均有持久成功回执，最终细节见下节和 `docs/reviews/2026-10-10-unified-session-release-receipt.json`。不得重跑已失败的旧 OTA 或使用旧包冒充候选。G6：真实登录 Web 周导航与相关页面通过，Mobile 模拟器/设备现场仍未验证；没有宣称客户端已经下载应用此 OTA，也未申请 App Store/TestFlight 发布。外接与七天试用保持未完成，不因发布成功改变状态。

## 首轮统一候选发布实绩

候选 ef64fb9d351ad955d4a37b2c55f1dc73c0f09e5e 的完整 CI 37964382737 attempt 2 全绿。首轮 live-change 检查要求本 SHA 的真实模型证据，补齐后仅重跑失败 CI：62 个离线场景、5 个在线场景通过，10 次 API 计费审计调用全部成功，未发现基线退化。未关闭或放宽 Gate。

可信 validate 37966219466 成功。首次授权轮换漏执行旧授权退休，库存预检查拒绝；未产生 intent、归档、新工作区或业务租约。独立复核允许补齐前置后继续：canonical revoke 旧身份、核对公钥后销毁旧 loopback 私钥、保留原失败日志及成功终态/锁身份，再安装新 SHA 授权。首次失败日志摘要 f806f341c6f977f911223d6386dce5d1dacbe640a8fb2b9834f57d60a20a6f6b 原样保留。

后端 Trusted release 37967680330 attempt 2 成功（首次在访问生产凭据之前因 GitHub 元数据读取失败停止，未消费部署）。服务器 completed.json 精确 SUCCEEDED、生产 HEAD 精确候选、健康度 60/60、四个服务 active、内网 /health 和公网 /api/health 200，新个人/健康导航未登录均 401；发布租约释放。

Web 独立操作 86cb1a54961245c789cc89e4204cbcff 生成 FRONTEND_SUCCEEDED，前端树 4dd6ebaa2fa84e1b009354f60c47edfa88a07153、制品摘要 79b77fe2592a02910c34c86d163c15fc8546890aeb1740b5f6f16ac3c6ac9da6。锁定依赖的实际 Next 生产构建及内外网 privacy/connect 页面核验通过。实际已登录 Chrome 复验：环境 404 恢复；个人工作区读取 revision 0 并切换周计划；仪表盘手动卡片、趋势坐标轴及非空 SVG 路径；运动详情非空心率区域曲线。生产未新增测试任务或修改健康记录，现场截图只保存在临时目录，不提交健康载荷。

OTA validate 37969771532 成功，canonical 目录/ACL 问题已解除。publish 37971203861 在 publication 阶段阻断：服务器 ota/<sha>、claim、租约均不存在，GitHub audit artifact 数量 0，没有可恢复的 vendor receipt。不得把泛化日志或短耗时推定为具体根因，不重跑此失败 run，也未执行第二次 vendor update。现有发布器把 claim 前阶段异常全部泛化且不归档安全诊断；本次继续补充闭集诊断和无 export/claim/update 的只读供应商准入，保留全部安全 Gate，修复后的候选需重新审查和 CI。Mobile OTA 发布尚未完成。

诊断改进先取得失败测试，再完成实现；新鲜发布工具验证 195 passed、1 macOS Linux ACL 不适用 skip。独立 ota_diagnostic_review 对四个固定文件摘要裁决 G4 GO。validate 现在包含受既有源码和精确 CI 闸保护的认证只读供应商准入；未增加发布次数或放宽单次 claim/回执恢复规则。下一候选须先完整 CI，再执行该只读诊断，确认前置条件后才部署和发布。

6d7d2513acc64d9f6058c5497a56dd7bfd719c75 完整 CI 37973005464 全部 30 jobs 成功，独立 lifenav_readiness 对固定 commit GO。只读 validate 37974122743 的审计诊断明确阻断于 environment，baseline/cohort/channel 全部通过；未 export、claim、RPC 或 update，未轮换生产授权。相同本地只读 GraphQL 请求通过既有 Expo CLI 会话验证：Python 默认客户端标识 HTTP 403，明确 reva-trusted-ota/1.0 后 HTTP 200、环境校验 PASS、项目及账号环境变量均为空；固定 manifest endpoint 同样从 403 变为 204（当前无适用更新，不能视为 manifest 成功）。两处请求补充诚实稳定的客户端标识，保留 TLS/代理/重定向/环境白名单/manifest 字节验证；先失败回归再实现，197 passed、1 macOS 不适用 skip。最终候选仍须独立复核、完整 CI、真实只读准入，不将本地兼容验证冒充线上发布成功。

## 最终发布回执与剩余验收

最终候选 b5e96ee84236b7ecdcd2de4914fbe6e2d13b432b 独立安全 GO，完整 CI 37974764859 成功；OTA 认证只读准入 37975652253 返回 ADMISSION_PASSED，Trusted Release validate 37976487728 成功。规范轮换 ef64 → b5e96 成功，原失败日志、旧后端/Web 终态及 launcher inode 7777226 保留，旧 loopback 私钥销毁。

后端 run 37976912480 成功，服务器 completed.json 为精确候选 SUCCEEDED；最终内外网健康接口 200、两种导航未登录 401、四服务 active、业务租约不存在。Web 已成功制品树 4dd6ebaa2fa84e1b009354f60c47edfa88a07153 与最终候选完全相同，保留独立发布回执 86cb1a54961245c789cc89e4204cbcff，未重复上传相同应用树。最终 Chrome 实际读取个人工作区并切换周计划，生产未写测试数据；截图保留本地，不提交用户载荷。

OTA publish 37977844821 取得原 vendor receipt 后在核验命令阶段失败，保留工作流 failure 与完整审计 artifact，未重跑 workflow 或 vendor update。原 group a87acf6d-c6b8-4ece-9390-97afaad6973e、update 01a12214-45b0-7fba-aea3-3259bc232c1a 的独立供应商回读通过；生产 canonical manifest 核验确认 update/runtime/project/bundle/全部 assets 相同。仅执行 canonical trusted_ota_server.py 的原双锁同回执 recover，最终服务器 OTA completed.json 为 SUCCEEDED，intent 摘要 4b7c5dd9b2d3577ab0eb9f16359855fd37691dcc498b79ae9345fe02711f6f38、receipt 摘要 793fa207194ad54234daafd1eac0a86ee7862dd1c34f678be8d96ba2bf441fcb，持久租约归档通过，原业务租约释放。工作流失败不被改写为成功，服务器恢复成功与之分别记录。

代码发布与用户使用验收分别记录：Web 现场已核验；iOS OTA 的发布与 manifest 字节证明已核验，客户端实际应用及 Mobile 现场仍未验证。外部接收方联调与完整七天使用不是此次可即时完成的证据，所有外接开关仍关闭。两份原视觉验收文档已从保留的 stash 恢复到原路径，旧地图未覆盖新地图。最终验收文档仅作为工作区证据更新，不推进已发布的 main SHA。

## 下一批统一发布候选（2026-10-10，整合中）

沿用用户整合其他 session 并全部发布的授权，root 接回唯一提交和发布所有权；生产当前为 346035f78，新增 harness 主干 ec1d6c7c9 的精确 CI38022547083成功。旧5fe及346失败OTA保留，禁止重发或换SHA绕过；本批为新增产品行为候选，须自己的完整Gate。

本批范围：Garmin未完成同步状态真实性、本人当天刚才运动候选查询（不确定具体运动身份）、补剂旧ID批量API显式actual_dosage及落库回执和双端类型、Mobile新对话/附件/依据栏UI、缺热量草稿如实展示、LifeNav Web日期/任务/撤销重做/离页保护及聊天首页入口。相关各Dossier的局部PG/测试证据保留，固定SHA安全审查与完整集成待执行。

排除未完成内容：daily_plan_chat及agent_executor混合改动缺授权真实模型闸，保留未提交；图片补剂完整识别确认写链路与热量识别根因尚未完成；外部Agent grant仅提案未实施；锁屏模拟器工具独立未验收。不把这些未交付项冒充修复，也不读生产秘密。候选冻结前仍保留所有其他session源码/原始收据。

固定首候选ea86f74fe独立G4 NO-GO：全局Next Link与客户端返回会绕过原beforeunload丢草稿。新增真实Navigation+workspace集成4项RED后修复：dirty时document click capture阻止取消的站内Link；window popstate capture在App Router前取消并恢复原路由/tree，保留同页hash与新标签行为；工作区出口复用Link避免双重整页提示。新8项回归GREEN，后续固定修正候选重审；未推送NO-GO候选。冻结ea86全量Mobile发现旧新建文本断言不适配图标按钮，保留失败并改为可访问label+实际回调验证，不放宽新建行为。

固定候选完整release-invariants在485项通过后发现新增recent-workout回归未纳入原r-other CI目录，真实exit1；保留/tmp/reva-next-frozen-ci-mode.log，补原catalog显式条目，不删除原覆盖。PG首次库名不含test被保护拒绝；修正库名后initdb默认SQL_ASCII导致中文DDL注释编码错误，保留两次失败日志，测试服务器均正常停止；后续明确UTF8隔离库重跑，不据环境失败宣称生产故障或PG通过。

冻结产品树PG验证112项通过、2项真实Pi链路未进入模型调用；发现副本缺少已有锁定Pi依赖目录，补齐复用后只重检这两项。当前不算PG总闸通过，原失败与环境断点保留。

## 新批 G5 终态核验阻断

固定候选 fa4703060594472933bca35553c9de05c5016cd6 已提交和推送。新鲜本地 CI-mode 发布不变量 2844 passed、20 skipped、84 subtests、exit 0；Web 全量538 passed/1 skip、Mobile全量3412 passed/1 skip，双端TypeScript通过；PG完整运行112通过2项因冻结副本缺既有锁定Pi依赖失败，补齐原锁定依赖后同两项PG补验通过。保留原失败而不宣称单次114全绿。

CI38028857846汇总completed/success，但backend-quality job114145419234及REST/check-run/GraphQL仍in_progress、conclusion和completed_at为空，尽管所有step含Complete job均success。独立lifenav_readiness裁决G5 BLOCK：步骤、workflow汇总及本地测试均不能替代该作业最终可信回执。完整full发布器只看汇总的形式通过不消除已知冲突；未轮换、未部署、未触发本批OTA，不换SHA、不重跑来绕过。等原job/check可信终态收敛后再复核。当前生产346035f78成功终态、clean、四服务active、无业务lease已回读。本地验收文档不提交推进main；详细证据追加于原统一发布receipt latest_attempt，原历史回执保留。

原fa470作业终态于后续可信REST回读已恢复completed/success，completed_at=2026-10-10T05:53:04Z；此前缺失终态及传输EOF原记录保留，未重跑或换SHA绕过。用户随后截图触发新的本人病程恢复修复，8338aa6d1固定runtime独立G4 GO、6331相邻+878分类器+46PG与36完整Pi集成通过。仅新增四个干净backend文件、独立回归和Dossier；混合executor/今日计划等继续排除。新候选需自己的完整CI、部署和原渠道OTA，未发布前不确认线上修复。

## 637520e25 最终候选与原样保留的发布失败

G4 GO，G5 CI准入 GO：本人病程恢复修复已纳入候选，真实Pi链路测试使用合成provider；36新测试、6331相邻回归、46 PostgreSQL测试通过。本地CI-mode 2844 passed、20 skipped、84 subtests；精确CI38030652894全部31 jobs completed/success，独立核验确认main与候选一致。

授权轮换成功并保留原346成功回执和锁inode。Web同主机制品a49b9258db5b42ef92bb519dcc4c65c4已READY，绑定完整树21087a159231ee621661816cc4e6afa3bada58c6和artifact_digest ea739cbea7539622466647c7a16c1148a183d469d84a2babee4fee9893ef7d0f；只准备，未消费或切换。Trusted OTA validate38031168634成功，未dispatch publish。

G5/G6 BLOCK：backend38031474956失败，固定637终态NEEDS_OPERATOR。健康评分60/60但独立硬闸agent_runtime_circuit=paused:reconciliation_detected:generation8:ack7。只读控制面显示1条missing_receipt未决Run（12:24开始、12:33 reconciliation，早于发布），uncertain_operations=0不证明无副作用。自动回滚后生产clean346035f78，四服务active、lease不存在，内外健康200。Web publication与637 OTA目录均不存在。

独立评审要求真人管理员先审核原未决Run的证据与实际效果；resume只ack精确代际，不结算未知结果，不能为通过发布闸自动执行。保持暂停，不重放写入、不重发失败SHA、不发布Web/OTA、不撤除恢复身份、不修改原NEEDS_OPERATOR或旧失败记录。具体回执见统一release receipt latest_attempt；该证据更新只留工作树，不推进已验证候选。

## 用户再次授权的全 session 清点与本地整合

2026-10-10 用户明确授权所有 session 修复代码合入 main 并发布。已逐项核对工作树、分支和现有 session，不合并历史未审临床 PR，不覆盖其他 session 的证据或私密验收截图。Workout 三个原提交 2ab5bd9e9/ef53e17e8/e2e75519a 合为本地主干 2be02053b/d699c3a61/8b4d033bc；缓存归属分支运行逻辑已存在，局部重复定义在 cacd20c31 去除，相对637不改变缓存行为。语音6bc52c309及e3af70ea6与main当前修复重叠，冲突核对保留更新后的清理/短句/异常测试，未重复提交运行代码；四套72tests passed。Workout测试修正完整Garmin成功返回契约，缓存与Workout组合67tests passed。独立固定cacd20c31 G4 GO，仅覆盖Workout整合。

其余本地今日计划、图片补剂失败提示与锁屏模拟器工具继续纳入统一候选；不是声称图片识别完整修复。外部Agent grant仍仅提案，未新增授权。锁屏工具19本地tests通过，当前Mac实际unlocked，不能声称实际锁屏验收通过。微信桥接分支eeaa3a8bc仍在原session开发；其新Linux隔离/独立固定审查及跨family审核未通过，保持draft/未部署，不使用旧commit的GO代替。

原生产missing_receipt Run的只读补充证据：user sealed计划1项，health_record状态rejected、0回执；assistant有1条verified/create回执。闭集资源核验显示资源存在、归属匹配、assistant会话绑定和回执时间在attempt窗口，但持久化资源operation identity不匹配。仅输出布尔与计数，未读取正文/原始健康值。不能推断NO_EFFECT，也不能据此确认该Run完全成功；既有无Operation的Run无安全结算入口，仍需真人审核，不直接改DB、不补造Operation、不自动resume。

部署/OTA阻断原样保留：637失败终态NEEDS_OPERATOR、原自动回滚及所有失败历史不变，真实模型G3缺授权凭据。最新固定候选还需全量CI-mode、精确main完整CI、独立G4/G5以及失败生命周期闭合。未推送本轮本地整合，不执行第二次637发布，不用新SHA逃避原状态。

## f343 本地固定验证与加载器修正

独立固定 f343706ca G4 GO，限源码而非 G3/G5/G6。整合后 PostgreSQL 129 passed，测试库正常停止；语音72、缓存/Workout67通过。System Map、202份Dossier和新增文件秘密扫描均通过。真实 simctl+xctest 系统设置启动/点击/滑动/截图 exit0，目录0700、回执0600；实际锁前后均unlocked，源码SHA为空且Reva业务验收unverified，不能替代锁屏或候选功能验收。

固定副本以PYTHONDONTWRITEBYTECODE=1运行原CI-mode release-invariants，545 passed后1 failed（404.96s）。原失败在test_public_host_boundaries的动态测试load未注册sys.modules，导致无缓存时_host_hardening_evidence的失败归档分支KeyError；旧字节缓存使该分支提前BootstrapError掩盖加载器问题。只修测试loader按Python正常import协议先注册module，再exec；不修改生产bootstrap、安全校验或失败终态。相关192tests passed，但原CI-mode失败仍保留，修正候选需无缓存固定副本完整重验。

微信桥接精确eeaa CI38034927895已终态failure；systemd249通过，但release-invariants的另一合成unit因credential private mode断言失败。原owner仍开发中，禁止合入红CI或使用此前draft GO。

加载器修正后的无缓存单项继续暴露原测试只捕获BootstrapError，真实失败归档路径按模块契约抛RecoveryError。保留该失败；进一步将fixture源码复制到独立临时目录、禁字节缓存，并校验具体unknown host recovery history理由及真实加载模块的RecoveryError类型，避免无关缓存守卫让用例假通过。最终相关192tests passed（4.83s）。已主动中断明确仍红的c585全量进程，197passed/KeyboardInterrupt、exit2（106.82s），不冒称通过，不再等待已知失败执行到末尾；最后修正固定候选再完整验证。生产bootstrap或历史恢复代码始终未改。

## 最新微信已提交代码的本地主干整合

用户再次要求继续推进，并明确本次无需 Claude 审核；该裁决仅限本次任务，不修改全局治理。保留已有独立安全审查与真实测试要求，不增加替代外部审查前置。

冻结微信分支 cfc996e7495e0d3bb9eebf9610694ec9bd97dac2 合入本地 main，原 owner 工作树干净；仅整合已提交代码，不覆盖其后续工作。其精确 CI38038910636已无失败或待运行检查；此前33be868的失败记录保留。合并无冲突，不启用服务、创建秘密、发起扫码/OAuth或改变生产权限。生产适配器、发布历史准入和开机启动仍未交付，微信实际收发未验证。

组合验证：桥接/生命周期/事务/历史/安装器479 passed、1 macOS环境skip；Web授权页20 passed；秘密扫描、203份Dossier与System Map通过。首次混合测试未指定测试数据库而连接本机PostgreSQL失败；修正测试配置后又发现原backend虚拟环境缺MCP依赖，两个启动失败均保留，不宣称通过。改用已安装仓库精确mcp1.30.0、pydantic2.12.5的既有测试环境，在独立UTF8 PostgreSQL17运行OAuth与既有隔离/今日计划/Workout回归；结果待实际执行记录。独立固定合并评审、合并后的CI-mode与精确远端main完整CI仍须通过。

2026-10-10 16:57 Asia/Shanghai的新鲜只读生产核查：clean346035f78、四服务active；637 completed.json仍NEEDS_OPERATOR，GitHub38031474956仍completed/failure；launcher inode7777226保留，瞬时/proc/locks未观察到被持有，business lease不存在。runtime仍paused generation8/ack7。原标记与旧回滚证据保留；租约不存在不构成收口。原发布由本线程负责，有效管理员审核及本场景受审收口入口仍缺失。未重试发布、撤权、改回执、清锁或resume，G5/G6仍BLOCK。

## 合并固定评审发现的失败历史准入修复

715976493的独立G4 NO-GO：dormant安装入口只验证当前生产SUCCEEDED和lease缺失，publisher已经installed之后若其backend失败回滚，仍可能放行安装；这是P1，不因不激活应用而豁免。已中断该已知NO-GO候选的CI-mode，原记录260passed/KeyboardInterrupt、147.47s、exit2保留，不宣称通过。

先运行实际inspect合成回归：旧production成功、publisher installed、publisher或另一SHA的STARTED/NEEDS_OPERATOR、lease缺失；旧实现错误进入后续package检查，1failed。修复复用canonical bootstrap的_retired_history、_assert_known_activity、_workspace_evidence和_recovery_process_proof：launcher锁内先检查全部受审历史和当前publisher终态/残留进程；取得lease后首次主机修改前和payload结束后再检查。未知结果保留audit/lease，不把原失败改成功，不推断空lease等于已收口。新增post-claim未知历史拒绝安装回归。330相关tests passed（15.11s）。修正候选需新的独立固定G4及完整CI-mode。

组合UTF8 PostgreSQL17实际155passed（130.86s），包括remote Health OAuth26、今日计划29、Workout15、Garmin33、账户缓存52；测试库已正常停止。该证明覆盖真实SQL方言与授权owner/过期/策略变更，不代表生产凭据、微信收发或锁屏验收。生产未修改，live模型证据仍缺配置；最新离线live-change检查确实failed/confirmed=false，未虚构确认变量。G5/G6仍BLOCK。
