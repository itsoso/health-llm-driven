# 小气候名称、图标与剩菜修正续接

| 字段 | 值 |
|---|---|
| 状态 | shipping |
| 当前阶段 | S7 后端和 Web 已上线，iOS 281 已进入 TestFlight 内部测试；正式 App Review 仍 BLOCK |

## G1 准入

裁决：PASS。用户明确要求将 App 名称、图标和应用内“小巴／小巴健康”统一为“小气候”并发布；随后提供剩菜照片补充餐次后被误拒绝的截图。本次维护既有品牌展示及饮食修正入口，保留 Personal Health OS 定位、认证与 AI 同意、本人范围和保存确认边界，不新增诊断、治疗或自动写入。

## 范围与实现

- Mobile、Web、Watch、mini-program 的现有用户可见名称与说明统一；稳定 Bundle ID、项目、协议和历史输入兼容保留。
- 最终图标采用青绿色底、米白云朵与暖杏色云瓣，源图 `docs/design/xiaoqihou/app-icon-v15.png`；同步原生图标、启动图、Watch 图标和会话头像。Web 图标作为编译路由 `/icon.png` 随候选制品发布，保留发布器对 public 配置的限制。
- 新名称同步语义入口，旧名称只保留在历史输入识别中。新旧三种称呼均验证 capability 问句不写入、明确请求可识别、否定与第三方指令不能写入。
- 开场建议润色和预生成缓存升至 v3，账户删除检查同时识别旧新版本，按精确 owner 槽位检查，不读缓存健康正文。
- 截图路径可在本地复现：初次附图触发剩菜澄清，按提示发送无图文字后原实现跳过专用分支，落入普通查询。新增完整当前请求匹配；只允许紧接已完成的专用澄清回复，在同一认证用户、会话、本地日期及30分钟内使用唯一照片。过期、插入其他对话、餐次或日期冲突、其他用户、无图、多图、未终结回复均不能接续。
- 续接仅生成原餐修正草稿；原餐仍须本人、今天、唯一餐次，餐前照片及原始份量可核验。保存仍通过原 revision 检查与确认命令，不新增一餐、不自动修正截图中的真实记录。

## 验证证据

- 语义与安全边界3589项通过；品牌受影响后端测试5836项通过，首次2个过时测试断言已修正，相关修复组合266项通过；新增续接流首次因无图参数为 None 失败，修正后剩菜完整46项通过。上述集合有重叠，不合并计数。
- Mobile42个受影响套件中41个通过，剩余分享图套件的旧名称负断言修正后8项通过；Web90项、Watch63项通过。Mobile/Web TypeScript、Mobile设计检查、API生成类型漂移检查通过。
- 缓存新命名空间先出现6个预期失败，再修正精确 owner 匹配；其他用户不计入本人数据。
- 真实模型闸初次因本机未配置 provider 及回退目的地未披露而失败。使用生产已配置的阿里云服务、合成夹具与内存测试库重新运行全部通过：invariants12/12、health_agent_core50/50、orchestrator5/5、trajectory12/12、golden9/9；不豁免同意/披露，不读取生产健康记录。
- PostgreSQL 隔离库49项（包含流式与集成）通过；初次夹具误用带时区时间写入 naive UTC 列，修正夹具后通过。独立 G4 审查进行中。System Map、秘密扫描通过；无结构变化。发布仍须目标精确 SHA 完整 CI 和受审入口。

## 商店状态与发布断点

App Store Connect 的 App 6763569720 可编辑名称已保存并回读为“小气候”，证据 `docs/reviews/2026-10-27-xiaoqihou-name-receipt.json`。这是草稿保存，不代表公开名称更新。新图标与原生名称需要新安装包，不能通过 OTA 宣称完成。

先前 v2 品牌范围独立复审 GO（`5b45d4ca0..6dc847ca0`）仅覆盖旧范围；当前 v15、全应用文案和续接修复必须重新审查。已有商店 build、旧截图和旧资料不构成本次原生验收。提交资料保持 preparing，未提交 Apple 审核。

已将 origin/main `12edbb30e` 非破坏合并到 main，保留已有发布文档与 benchmark 修改；本次只暂存自身变更。候选已推送，干净源码的模拟器原生构建进行中；尚未部署、上传新商店包或公开发布。

商标尚未申请或缴费；申请所需主体资格材料尚不具备，个人资料不进入仓库。商标与 App 显示名称是不同状态。

## 安全审查修正

首轮固定候选 `49eafbe9e` 为 NO-GO：续接源说明只用日期否定词表，遗漏“昨晚”、显式日期、他人餐食和撤销/假设说明。新增8条断言先全部失败，再改为完整源说明语法，仅接受本人当日餐食的有限明确表达；未知附加说明要求重新附图，不再用缺少否定词推定今天。另补截图原话、附图标记、第三方和假设的回归。源图上传日期、餐次和最终确认边界仍独立检查。首轮审查其余品牌、隐私和发布边界未发现阻断。新候选需复审 GO 后才推送。

商店草稿说明已同步新名称并读回，en-US description 无旧名称；未送审、未改变线上商店状态。

## 复审与最终局部验证

独立复审对 `8d1d1b1b`、累计范围 `12edbb30e..8d1d1b1b` 给出 GO；独立剩菜与缓存119项通过。扩展 PostgreSQL59项通过，真实模型闸再次全部通过。截图原话“今晚”与用户照抄示例的“午餐”存在冲突，不能直接修改午餐；进一步修正初次澄清示例，使明确晚餐说明建议补充晚餐，无明确餐次时提示填写实际餐次，不再固定举午餐示例。该提示仅澄清，不授权读取或写入；新增断言先失败。

`e8be03fbc` 的澄清修正获得独立 GO，剩菜60项通过，真实模型全套再次通过。完整 CI run `40494169829` 中仅 backend-test-balanced-05 的旧缓存版本断言失败，汇总闸随之失败；修正该断言为已实现的 v3，不改变生产代码。相关撤权、预生成与账户删除106项通过。保留失败运行，最终候选需重新取得精确 SHA 完整 CI 绿色，才可发布。

模拟器 Release 原生构建成功并安装，名称回读为小气候。视觉检查发现登录页仍使用通用心形标识，补为同一云朵图标；登录行为不变，现有登录回归48项通过。此处及以上为发布前过程记录；最终交付事实见下节。

## 2026-10-27 最终候选与实际交付

候选为 `8f7d94696424f92ff57243edb906cd6d2dd14a3a`。独立安全复审 GO，精确 SHA 的完整 CI [40496844800](https://github.com/itsoso/health-llm-driven/actions/runs/40496844800) 成功；发布 validate `40499788048` 成功。最终模拟器 Release 源码与候选的1055个 tracked mobile 文件相符；实际模拟器版本1.3.6、build 1，不冒充商店281包。登录、今日计划打开关闭、个人中心隐私页、登录云朵标识及桌面名称图标已实际验收。

- 后端：受审发布 `40500052228` 的 backend job 成功；生产精确候选 SHA、`completed.json=SUCCEEDED`、健康分60/60、公共 health 200、匿名 POST `/api/v1/agent/send` 401 独立回读通过。截图中的剩菜续接修复已部署；没有回放或修改截图中的真实健康记录。
- Web：无备份发布操作 `9a93b39ad8c546e8a5ee8379708cd459` 的持久回执为 `FRONTEND_SUCCEEDED`，artifact digest `92e9fbc11a01347304b5bf4594cfad76671597f2c76ace26670d73a27db6aa2b`；公共隐私和连接页含新名称、无旧名称，`/icon.png` 与候选文件逐字节相同。登录路由为客户端页面，初始 HTML 没有品牌文本，不据此声称完成该页文字视觉验收。
- iOS：EAS build `a40a61f3-02db-4a88-a308-56884c53500b` 为 FINISHED、IOS、STORE、production，版本1.3.6（281），source SHA 与候选一致。下载的实际 IPA 名称为“小气候”，bundle `life.executor.health`，SDK `iphoneos26.5`；图标已视觉核对，App Store 分发描述文件 `get-task-allow=false`。IPA SHA256 为 `43a880c1a7f252ca75d17589fd25cc4ac4cc99e1911a3d7fd5f39aeda1eec356`。
- 上传：submission `74009f8c-7450-4ac1-a73b-7a57fc919539` 返回 ERRORED/UNKNOWN_ERROR，原 workflow 的 testflight、release-result 失败记录保留，没有重建、重传或清消费标记。Apple API 独立确认 ASC build `bba28f43-cc87-429b-a23f-0babcdb98245` 为 VALID，1.3.6（281）处于 `IN_BETA_TESTING`，已在 `Team (Expo)` 内部组；外部测试仍为 `READY_FOR_BETA_SUBMISSION`。这是 Apple 实际接收和内部可用证据，不把原失败 workflow 改称成功。
- 商店资料：API 保存新名称、说明与 Review Notes；TestFlight 更新说明已保存。1.3.6 草稿关联281，仍 `PREPARE_FOR_SUBMISSION`、MANUAL；没有提交 App Review，也未公开发布新商店版本。
- 收尾：后端和 Web 服务 active，业务租约已释放；本次受限 SSH 授权已精确撤销、loopback 私钥销毁，长期复用的 cloud secret 与 Expo token 保留。原部署、上传和失败审计均保留，没有创建备份。

实际证据汇总：`docs/reviews/2026-10-27-xiaoqihou-release-receipt.json`。相关测试集合存在重叠，不能相加为总测试数。

## 正式 App Review 的剩余阻断

G5：后端/Web 与 TestFlight 内部发布分别有实际证据；整体 workflow 汇合仍失败。G6：BLOCK，未声称完整商店上架。

1. 上传工具错误与 Apple 接收成功需要按受审流程收尾，不能重新 dispatch 原上传或据此绕过正式送审闸。
2. 审核账号可以登录且有演示数据，但固定简报不是默认最新会话，端到端 live-demo 检查失败。历史 reset 为已接受 UNKNOWN，已有行政收尾明确 `demo_verified=false`、`reset_authorized=false`、`retry_authorized=false`；未重跑 reset 或旧简报修复。新的数据维护须遵循 `docs/governance/deploy.md` 中独立明确授权和受审新 attempt 的要求。
3. 新候选完整模拟器验收和人工审核后的截图材料尚未齐备；硬件不支持项继续依模拟器替代验收规范记录，不伪造真机通过。
4. 用户要求通过 API 构建和发布，已按此执行；当前隐私问卷发布状态、医疗器械声明及合同仍未取得完整当前证据，不要求用户再次网页登录，也不将其记为通过。

商标申请与上述发布无关，仍未申请或缴费。


## 2026-10-27 送审继续及最新范围

用户明确要求完成后提交 App Store 审核，并确认当前隐私问卷（含语音、照片、位置）已发布、医疗器械声明 No 已保存、Apple 合同有效。公开 ASC OpenAPI 4.5.1 没有完整可读的上述状态，分别保留用户确认来源，不能伪称 API 回读。

用户在“解决问题”任务追加左上角图标与剩菜流程优化，并明确要求协调；已读取该任务原始用户消息核实。该任务独占剩菜后端实现及安全审查，本任务独占聊天头图标及统一发布。281 / 8f 是已交付旧候选；新改动汇合并重新验证后才冻结新的送审候选，不重复上传281，不并发部署。

聊天头改用适合28pt的代码矢量云朵/暖色日光，移除小尺寸圆底、脸部细节与idle状态点；桌面及大头像资源不变。现有ChatHeader、EmptyStateHome共19项通过，Mobile TypeScript通过。新包模拟器视觉验收待执行。

审核账号新固定维护正在准备：`xiaoqihou-fixed-briefing-v1`，以当前8f生产代码、固定fixture哈希和新的精确CI操作者为边界，仅插入一条会话及两条夹具消息；旧数据不修改、不删除、不归一化时间。原279 UNKNOWN与两次未进入数据库写入的记录不变。独立目录、父子进程和锁证明、原子业务租约、资料快照、显式事务及提交后只读校验都必须通过；已有标识或任意不确定结果禁止重试。尚未执行生产写入，须待完整测试、独立审查、精确CI及新鲜inspect后取得该具体attempt的独立授权。


新维护 G4 首轮 NO-GO：已验证的 `/var/lock` alias 不能直接传给拒绝符号链接的 fsync；修正为先验证 lease 再同步真实父目录，使用实际 sync 与 alias 的回归通过。第二轮 NO-GO：易失 lease 重启丢失后，原发布历史聚合没有识别新维护目录；现将固定 intent→database-started→completed 完整链校验接入 bootstrap install/known activity/idle 与 server frontend/OTA 历史聚合，缺失、未知、畸形或多余文件均拒绝后继发布。维护执行还须验证实际 installed launcher 与当前受审操作者源码/策略逐字节绑定；先轮换安装带守卫的发布器，生产后端仍保持8f，才允许该独立维护。352项发布器/维护回归通过，另补实际 build/testflight claim 的无新消费标记负例。仍未生产写入；待固定提交复审。

另一任务固定剩菜源码 `ea779bbe4` 已取得独立GO并cherry-pick为 `e71083201`，与图标及维护范围汇合；本任务独占发布。汇合 `b256161a2` 干净快照真实模型闸通过（含synthetic consent、内存库、已披露阿里云服务），没有使用用户截图重放或读写生产健康数据。新发布器守卫改变后继续绑定最终精确候选；任何旧日志都不冒充最终版本送审证据。


## 83876750 固定候选与送审准备

最终应用候选冻结为 `83876750fcbb404255b7439482688fee82a490d4`，Mobile tree `fc943f6e0f1fa6cab9e3d0ae08a1ff749ceaea58`。完整 CI [40510498394](https://github.com/itsoso/health-llm-driven/actions/runs/40510498394) attempt 2 成功；attempt 1 的真实模型证据尚未完成导致 backend-quality 失败记录保留。干净精确候选真实模型回归完成后才重跑失败 CI job，未改应用源码。独立 G4 GO、783项 CI-mode 集成、秘密扫描及 System Map 检查通过。受审 validate [40513511069](https://github.com/itsoso/health-llm-driven/actions/runs/40513511069) 成功。

受审 launcher 已安装838，原生产后端仍8f。首次 bootstrap 预检将父包装进程识别为并发发布器，未建立 retirement intent；更换为 stdin 交付并 execve 交接的调用方式，保留互斥检查，第二次成功。没有重建、清理或覆盖未知发布记录。新简报只读 inspect 成功；固定 attempt 已提供完整合成内容预览，独立用户授权待回复，尚未写入数据库。

从本记录起，为正式送审建立838候选的生产 OTA 发布冻结，直至审核/发布收尾或用户明确授权替换候选；不沿用已解除的279冻结。本任务仍为唯一发布者。冻结前最后更新为 `01a17cee-3dd1-7225-9fff-709e7e3b5927`，group `d1bd9f69-fb5b-4d7e-af92-eed8bde772c2`，source `12edbb30e9bf30247dbcb2ac6635e3fee322754a`，runtime1.3.6，创建于2026-10-27T10:35:50.609Z。冻结是后续发布限制，不更改既有用户的更新通道。新IPA仍须核对embedded update时间、实际权限及签名。

模拟器Release1.3.6/build1的1055个Mobile文件与838逐字节相符。实际通过登录、Today打开关闭、个人中心隐私页、导入入口、前后台草稿保留以及小尺寸云朵视觉检查。截图来自合成演示账号；硬件/第三方集成未验证项仍需完整列举并绑定最终IPA，不冒充商店包或真机通过。新商店构建、最终资料及正式送审尚未完成。


独立原生范围复核 GO：旧GPS候选1ba724dc至838的实际production/ios配置执行结果仅品牌与颜色差异，GPS usage/background modes、HealthKit/APNs、Bundle ID、associated domain、runtime1.3.6及生产排除Rokid/Siri/Watch不变；eas.json逐字节一致，直接原生依赖与本地原生模块未变，JS/工具依赖变化不增加原生权限。独立65项配置、图标及Watch插件测试通过。最终IPA策略仅拟新增精确838白名单，仍逐项检查真实制品、签名和候选GPS风险接受；该策略不能代替实际新包验收。策略修订先RED（仅新候选case失败，未知来源拒绝仍通过），最终固定策略提交及复审待原生发布结束后进行，不推进或替换当前应用候选。

## 2026-10-27 维护完成及 282 上传

用户已明确确认固定新 attempt `xiaoqihou-fixed-briefing-v1`，按原 inspect digest 执行一次并完成 `VERIFIED_BRIEFING_ONLY`；只新增一条合成演示会话及两条消息。旧 UNKNOWN 历史保持，未重跑。新完成回执摘要 `e232998b0a6eb70995a0c5695f57d1df5dae2f0d5a5fa028f3693f653b006cf5`，live demo 检查通过；模拟器实际默认会话显示固定简报。

唯一发布工作流 [40517861529](https://github.com/itsoso/health-llm-driven/actions/runs/40517861529) 整体成功；生产 HEAD 和 durable `completed.json` 独立读回 838 / SUCCEEDED。EAS `267aad01-a185-4343-b0fb-13ee7e8fabc7` 为 production / 1.3.6 (282) / 精确 838，上传 `91cdf464-0aa9-4a91-a800-e4c346933b21` 成功。Apple build `f224685f-e589-41ea-a9d3-fa337b85269a` 已 VALID / APP_STORE_ELIGIBLE。尚未正式提交审核。

用户新反馈“推送的 context 没有带入”已纳入本次送审前修复，来源链路和失败/修复记录见 notification-detail Dossier。原生包保持冻结；后端修复与仅增加 838 白名单的原生检查策略另行固定提交、安全复审及 CI，完成后核验与原生 282 的组合。不得将 Apple 已处理或已有截图等同最终送审通过。

实际282 IPA已下载并核验，SHA256 `05af6f2510c74648ca5991b1578612438774253052bf68aad1ddc7bafd4d5732`，显示名小气候、云朵/暖色日光图标实际可见，Bundle ID、签名team、APNs/HealthKit/associated domain与受审范围一致；仅location后台模式，iPhone portrait，Xcode2660/iOS26.5。实际制品验证器通过。embedded update `2fda6a22-1167-4e7c-b99e-58f443d7203f` 时间1793110673505晚于冻结前最后OTA，冻结仍有效。

七张合成演示账号截图已按838源/模拟器实际build1准备；其中五张已通过ASC API上传并处理为COMPLETE。旧五张尚未删除、顺序尚未替换；draft仍选择281，282尚未绑定为送审版本。候选绑定模拟器证据列明5项真实通过、17项未验证及GPS三项硬件残余风险，保留用户明确接受的模拟器路径；它不豁免当前通知问题。CUA服务后续多次timeoutReached，未冒充新UI验收。

通知修复973已完成本地验证，推送因远端备考服务c487新增迁移而被拒绝。已停止外部写入并等待并发发布交接；App Review未提交。详见通知Dossier。商店资料已更新282实际身份但保持preparing，未将安装包处理完成等同发布验收通过。


### 2026-10-28 送审依赖状态

282构建已上传并完成Apple处理，原生内容仍冻结838。统一接管发现另一次a8后端发布
在新exam表权限校验处失败，生产服务停止；本轮先准备固定前向恢复，细节见
[通知详情Dossier](2026-10-18-notification-detail.md)。未重跑失败发布，也未提交App Store审核。
恢复完成后仍须闭合失败身份、部署通知修复并验证最终用户路径，之后才执行已授权的API送审。

2026-10-28 07:30 +08:00：统一候选61cd完整CI [40600694655](https://github.com/itsoso/health-llm-driven/actions/runs/40600694655)通过，canonical服务器源码已检出。首次凭据默认只读inspect在网络依赖关系检查拒绝；未mint新token、未消费凭据/恢复attempt，数据库与服务均未变。现场证明三个业务service因原runtime boot gate禁用而仅保留Before=shutdown.target，原验证器期望的multi-user.target隐式关系已消失。修正限于既有GateView的精确状态转换，原runtime/network证明代码保持不变，未知关系继续拒绝；重新固定候选、独立G4和CI后才推进。

同日App Store API已选中原生282，替换并排序五张新截图，逐张COMPLETE回读；没有重复构建或上传。年龄分级、审核联系资料、免费价格及中美可用状态已读回；隐私/医疗声明/合同沿用用户明确确认。282与61cd源码/API兼容独立GO，旧客户端204项、隔离PostgreSQL兼容97项通过。新主干的备考UI不在冻结282内。模拟器CUA再次timeoutReached；旧截图不升级为新鲜验收，通知线上已知失败和最终送审仍待闭合。

2026-10-28 07:55 +08:00：52d2完整CI [40603132111](https://github.com/itsoso/health-llm-driven/actions/runs/40603132111)通过，807项CI-mode集成、769项恢复相关验证通过。canonical默认凭据inspect通过后，固定`exam-a8-read-credential-v1`完成`CREDENTIAL_REPLACED`，实际完整CI已核验；不可重复续期。后续数据库恢复默认inspect返回70，尚未消费恢复attempt或启动业务服务，正在只读定位拒绝原因。

同轮真实模型隔离API测试暴露通知协议纠错冲突：不合法的模型选择文档触发通用自然语言重合成，破坏通知JSON契约并以protocol_leak结束。新增正反测试先失败；修复将所选通知留在既有一次有界来源纠正路径，严格渲染失败的草稿先丢弃，最终来源、医疗、输出质量和持久化检查保留。本地通知及普通输出质量84项通过；真实provider首轮正常路径完整引用正文、401/404归属、流式与保存一致、零健康写入通过。真实provider这次没有触发纠正分支，不能冒称其通过；分支由定向正反测试覆盖。失败及路径误写的测试日志均保留。此补丁尚未进入冻结52d2，须独立审查、最终候选CI、部署及新鲜线上验收后才可送审。

- 2026-10-28 08:18 CST — 52d2 恢复 default inspect 的第二次源码证明失败已定位为 `_connect` 改变 cwd；原固定迁移仍 PENDING，恢复 attempt 未消费。新增两条 RED 后修复为 Settings 加载内 scoped chdir，成功/异常均恢复。52d2 已完成的只读凭据续期不可重放；新增共享历史绑定只允许两份精确原始回执、52d2 原 G4/文件摘要/到期时间一致，事故快照仅新 G4 可变，closure 复用同一验证器。当前相关验证 228 passed、7 skipped（PG lane 另补），未宣称生产恢复。
- 通知补测发现一般协议纠正与通知选择 JSON 契约冲突；通知改为仅使用已有有界一次 source-only 修复，移除非法草稿后再检查最终输出。84 条本地测试通过；独立 PostgreSQL 85 条通过，报告 `/tmp/xiaoqihou-notification-protocol-g4.md`。隔离 API +真实 provider 正常路径通过；首轮注入协议错误、第二轮真实 provider 纠正也 COMPLETE，完整来源、401/跨用户404、原通知不变、stream=持久化、零健康写均通过。这不是生产或模拟器验收。282/source838、已替换商店截图、OTA 冻结保持，最终送审仍待生产及使用路径验证。
