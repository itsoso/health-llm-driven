# 按发布目标验证与制品复用

| 字段 | 值 |
| --- | --- |
| 状态 | validating |
| 当前阶段 | S5 修复候选验证（此前基础设施发布已完成） |

## 范围与授权

- 用户授权按2026-10-09讨论的优化方案执行；primary controller为Health Harness，safety-gate负责独立固定提交审查。
- 基线main：`b567e18c0520e0be4cf44f1494a573b6bd85d589`。前一轮全量CI精确代码提交`af4ba8cfb70376945c25a845b870f2051528f9a9`，run37795770707用时644秒，28项job成功。
- G1：工程交付优化，无新增产品行为。发布许可属于安全边界，必须以目标、精确源码、必要检查及不可变制品证据约束；未知影响范围继续完整验证。
- 不修改另一checkout中饮食识别工作，不启用superpowers，不取消同SHA失败记录来制造绿色，不把PR或缺失依赖导致的skip当作发布验证。

## G1 工程优化准入

裁决：PASS。无新增产品行为；保留精确 main、独立安全审查与风险相称的 CI。目标门禁必须在可信服务端根据真实生产基线判定，不接受调用方指定范围。

## 交付顺序

1. 核查现有CI分类器、发布gate、可信服务器执行器与生产制品路径；定义目标检查集合及版本化证据。
2. 先实现并验证fail-closed目标门禁，再接CI范围选择；鉴权、数据隔离、健康写入、DB及公共契约保持必要阻断。
3. 接通至少一条真实制品生产、验证、复用路径；绑定SHA、目标、锁文件/工具链、制品摘要，不接受未验证外部制品。
4. 在已证明的边界内落实按依赖范围测试、测试环境复用和完整回归安排；runner容量只据观测评估，不擅自购买资源。
5. RED/GREEN、项目CI-mode集成、独立G4、主干精确CI与实际发布路径验证；记录仍未达成目标，不将脚手架或离线回放宣称为生产提速。

## 验收目标

- 日常反馈1～3分钟、普通后端可发布3～5分钟、已验证制品部署与冒烟1～2分钟是待验证目标，不是完成声明。
- 降低请求发布至可用的墙钟时间；分别记录排队、环境准备、测试、构建、部署、冒烟，不能只比较CI总长。
- 任一目标必要检查缺失、失败、取消、错SHA、错运行尝试、未知影响、制品不匹配必须拒绝。
- 旧发布入口不得因CI拆分而获得更弱许可；上线前必须证明兼容或显式拒绝旧协议。

## 当前证据

- SQLite 原夹具每用例创建/删除全部表；相同231项真实测试顺序对照32.14→13.90秒，均通过，墙钟下降56.8%。守卫版每用例独立engine/数据库；schema指纹失效、自定义DDL/连接事件保留原生命周期，备份失败显式失败。专属17项及CI-mode集成3项通过。PostgreSQL路径未改，真实PG证据仍待CI。
- 后端目标准入绑定实际生产HEAD及root-owned成功回执，累计至候选所有提交按严格白名单判范围。仅现有3个独立服务实现文件及限定测试/文档可进入backend-v1；未知、重命名、合并、测试夹具、依赖、迁移、安全、发布协议等变化仍全量。
- backend-v1保留全部后端分片、PostgreSQL、质量、类型漂移、发布不变量及文档闸；允许无关端侧仍运行，但任何已观察到的失败/取消/缺失/身份漂移均拒绝。旧入口默认full。当前协议改动本身必须全量验证。
- 同服务器预构建制品已实现：原sandbox实际构建、固定源码/工具链/配置绑定、root-owned READY、摘要校验、单次消费。Linux真实Next构建/消费新增并行CI job，本机明确跳过，不宣称生产可用。
- Python依赖锁复用原先已有。Pi npm冷/热对照只节约约1.6秒理想值，不足以引入新的失效复杂性，因此未增加缓存。跨runner CI前端制品直接投产因工具链/公开配置/隔离不同而不采用；本轮同host准备复用不算消除CI重复编译。
- 接线回归321项通过；审查中修复旧run消费资格前检查和已发布OTA终态收尾被新闸阻断的问题，并补充真实调用顺序测试。
- 此处为首轮本机实现证据；后续固定提交、主干CI和生产兼容检查见下节。1～3/3～5/1～2分钟目标尚未证明。

## G3 本机验证

裁决：PASS（本机可执行范围）。目标gate、scope、executor、bootstrap、workflow与CI合约594项通过；admission文件/Git对抗及邻近兼容530项通过（两组有重叠，不累计为独立案例数）。前端制品与发布邻近189 passed、3项Linux测试明确跳过；CI-mode集成和夹具守卫20 passed。System Map、Dossier一致性、diff检查通过。

部署脚本与发布邻近组合首轮395 passed/3 skipped/2 failed：两项失败均因启动环境PATH未指向项目Python3.12；同一失败模块补齐PATH后15项全部通过。未降低断言或修改业务代码。新pipeline完整CI、真实PostgreSQL、真实Linux制品准备/消费与生产启用仍待后续验证。

## 首轮 G4 与主干 CI

- 固定提交 `2c6ee449dc5f83aa183d46aaa320f7695744b530` 独立G4 GO（代码集成）；独立640 passed/1 Linux明确skip，另20项SQLite/CI-mode通过。审查未冒充生产放行。
- 已合入main，自动完整CI [37877803968](https://github.com/itsoso/health-llm-driven/actions/runs/37877803968) **30/30成功**；新真实Linux制品一次构建及无重编译消费 **1 passed / 114.40秒**；真实PG语义 **313 passed / 339.26秒**，真实Redis专项6 passed。
- 相同墙钟口径644→466秒（10分44秒→7分46秒），减少27.64%；runner分钟121.97→100.77，减少17.38%。新增两个job仍改善；这是单轮观测，非P95。详见 [机器证据](../reviews/2026-10-09-targeted-ci-performance.json)。PG job 442秒成为关键路径；3～5分钟目标尚未达成。
- Trusted validate [37878527903](https://github.com/itsoso/health-llm-driven/actions/runs/37878527903)成功。生产保持 `be8bd98e10db01241dd0b9e6e4c34181a9061345`，没有应用运行时代码差异。
- 新门禁生产只读验收发现真实兼容缺口：canonical源码与full CI均PASS，但生产Git使用固定同仓库SSH origin及合法历史branch metadata，被过窄配置表拒绝。未撤权、未轮换、未部署；保留该失败并补真实Git回归后独立重审，不修改生产历史配置来迎合门禁。

## 第二轮：生产兼容与 PostgreSQL 并行

- 生产Git仅额外允许固定同仓库SSH origin及合法历史分支的精确origin/merge绑定；canonical源码仍要求HTTPS和main。危险配置、未知项、控制字符、非法ref仍拒绝。兼容专项64项、邻近556项通过；父方新鲜admission/CI合约/CI-mode集成83项通过。
- 原PG语义清单按历史耗时分为两个有界子进程，共用已安装依赖，每组创建独立随机PG数据库、在线Redis DB13/14及pytest缓存。保留原超时、迁移与Redis专项；创建冲突不删除他库，清理失败仍红，输出独立JUnit和日志。
- 本机真实PG与在线Redis完整验证：146 + 167 = 313 passed，0 skipped，0 failed。独立收集原313个nodeid与两份JUnit并集完全一致，无重复。`/tmp/reva-pg-ci-20261009/selection-equality.json`保存清单核对结果。
- 本机首轮SQL_ASCII临时库不支持中文注释；改为UTF8重建专用临时库。隔离探针曾因macOS checkpoint导致DROP DATABASE超过30秒而红；只调整专用本机临时库fsync/synchronous_commit完成质量验证，CI的PG16与原30秒管理SQL超时保持不变。本机237.208秒不作为性能收益证据，真实收益待新完整CI。
- System Map、Dossier、秘密扫描和diff检查通过。System Map首次因shell PATH缺Python3.12退出，使用项目venv PATH后通过。此阶段第二轮固定提交G4及主干CI尚待完成，生产未修改；后续结果见下节。

## 第二轮 G4 与真实 CI

- 固定提交 `28b2471d72a3afdc7aba681bb5762dccfbae99bc` 独立G4 GO：173 passed、3项真实PG/Redis探针按审查范围明确skip；作者此前38项含真实探针通过。原20个selector与父提交不可变CI命令逐项相同。
- 已合入main，[完整CI 37880423513](https://github.com/itsoso/health-llm-driven/actions/runs/37880423513) 30/30成功。真实PG16隔离探针3 passed，原PG业务146 + 167 = 313 passed，原真实Redis6 passed和closure PG9 passed。
- PG并行runner184.613秒（原339.26秒），PG job 442→272秒。全CI墙钟500秒（8分20秒），比首轮466秒慢34秒，比原基线644秒减少22.36%。runner分钟95.47，比原121.97减少21.73%。最后分片13排队148秒、执行328秒成为关键路径；不能把局部PG提速宣称为全CI单调提速，不能宣称3～5分钟已达成。
- [Trusted validate 37881127428](https://github.com/itsoso/health-llm-driven/actions/runs/37881127428)成功；canonical生产只读admission成功，精确绑定CI run37880423513，修复真实Git兼容拒绝。
- 已按原规则撤销be8bd98e1授权、销毁旧loopback私钥，启动canonical新SHA轮换；当时正在核验历史发布证据，尚无部署成功回执；最终结果见下节。历史前端node_modules证据读取数GB是独立发布耗时点，本次不跳过或删除证据。

## G5 发布与 G6 线上验证

- canonical轮换成功，执行器安装绑定`28b2471d72a3afdc7aba681bb5762dccfbae99bc`。[正式后端发布37881761730](https://github.com/itsoso/health-llm-driven/actions/runs/37881761730)经原preflight/readiness后执行一次；服务器`completed.json`为该精确SHA的`SUCCEEDED`，业务lease已释放。服务器started→completed实际362.58秒（约6分3秒），不含此前授权轮换，未达1～2分钟目标。
- 生产Git HEAD为同一SHA，部署健康评分60/60，runtime-only KB serving contract通过。`health-backend`、`health-frontend`、`celery-worker`、`celery-beat`均active；内网与公网`/api/v1/health`均HTTP200。
- 本次环境配置及回滚点备份已执行。依据用户既有授权及`docs/governance/deploy.md`中`DEPLOY_DATABASE_BACKUP`默认关闭策略，**数据库备份、恢复演练和站外归档未执行**；不是本次优化新增豁免。过程说明曾将关键词误判为数据库备份阶段，已向用户明确纠正。
- 与原生产be8bd98e1相比，backend/app、frontend、mobile无应用运行时代码变化。本次不做Mobile/TestFlight发布，不重建或切换未变化的前端；前端prepared-artifact真实构建/消费已在Linux CI通过，未声称生产制品切换或1～2分钟部署达标。
- G5 PASS（精确CI及终态回执）；G6 PASS（运行版本、服务、公开健康及发布收尾）。本轮基础设施交付完成，性能目标部分达成；后续优化依据是晚启动的backend分片和历史证据重复遍历，1～3/3～5/1～2分钟及P95目标仍未证明，不擅自购买runner或削减安全/业务验证。

## 续轮：刷新夹具优化后的 CI 调度数据

- 用户继续优化授权；已保留并快进集成另一会话`a2323a0ee`视觉模型发布改动，对应主干CI37884822646成功。
- 原调度数据来自SQLite夹具优化前的run37793465362。本轮使用夹具优化后最近三次完整绿色run37877803968、37880423513、37884822646的每组首次成功进程wall time最大值；只改scheduling_seconds与来源记录，16个worker、60组选取、进程隔离、超时、重试均不变。CLI支持显式多run输入，独立核验GitHub身份后使用，归档摘要全部保留。
- GitHub真实归档部分worker仅含aggregate日志、缺少step日志；原工具误判不完整。RED两项失败后补兼容：每worker只选一份，双份遥测必须一致，重复/错worker/冲突仍拒绝，缺失/失败/重试样本仍不能更新目录。多run聚合另有RED/GREEN测试；重复run或执行策略不同拒绝。
- **单轮刷新否决**：在拟合轮回放最慢268.947→213.046秒，但另一轮267.975→297.495秒退化。两轮max候选在第三轮277.683→293.021秒也退化，因此最终统一使用最近三轮保守最大值，不选择最有利单轮。
- 三轮全部作为调度样本，最终回放最慢分别277.683→240.492、268.947→241.656、267.975→243.961秒。总进程工作量逐轮不变。**这些不是独立保留集或真实新CI总耗时**，新CI是最终裁决；证据见`docs/reviews/2026-10-09-ci-placement-refresh.json`。
- 本机日志/调度/CI合约、worker runner与CI-mode集成验证；System Map通过。等待固定提交独立G4及实际CI结果。
- 历史发布校验本轮不改：两次idle跨越durable intent，不能缓存可变证据或删除复验；同盘双并发收益未证明，且避免干扰另一会话视觉发布。此改动仅CI配置/遥测工具，合入即生效，无需重启应用或轮换生产授权。

### 续轮实测裁决与 runner 容量调整

- 固定10db27885独立G4 GO，独立56 passed并重算3份ZIP；父方80 passed。已合入main，CI37886141575实际30/30成功。
- **仅刷新16worker权重没有证明端到端收益**：463秒vs紧邻462秒；runner100.65vs96.17分钟；最慢测试步骤269vs268秒，worker排队累计643vs313秒。保留此结果，不宣称提速。
- 接续候选收敛为12个worker job，仍运行原60组独立进程和全部原参数。目的是在观测到的20个同时活动job约束下减少排队及重复环境准备；不是减少测试。同步固定required job集与生成矩阵的契约，缺失/失败/skip不放行，full gate不变。待独立审查和新CI裁决。
- 12worker实现RED 4 failed/197 passed，GREEN兼容321 passed；父方CI-mode集成3项、System Map、秘密扫描和Dossier检查通过。回执policy_version为backend-v1-workers-12，target/RPC保持backend-v1；默认full gate不改。实际workflow命令、默认CLI、目录worker_count及门禁名单均经契约测试对齐。

### 12worker 实测否决与恢复

- 固定259e97abf独立G4 GO，321项独立测试通过。CI37887237784实际26/26成功，全部60组仍运行；队列最大167→46秒。
- **性能NO-GO**：全CI463→494秒（7分43秒→8分14秒），runner100.65→99.07分钟，仅小幅下降，较本轮起点96.17分钟仍高。排队收益未抵消更长的串行worker；不因测试绿色就保留性能退化方案。
- 恢复为已审查、已实际CI通过的10db27885之16worker配置、planner、严格gate及相关测试；日志兼容修复和三轮有来源遥测保留。默认full gate、旧SHA策略、安全复验均保持原状。此轮没有证明端到端提速，不宣称达到3～5分钟目标。
- 未操作生产服务、授权、凭据或历史归档；另一会话视觉发布改动保留。后续应先做逐测试耗时/runner环境分段取证，再决定优化点，不继续盲调并发数。

### 恢复后验收

- e42686d4b独立G4 GO，独立245 passed、父方269 passed（含CI-mode）；8个执行配置/门禁/测试文件与已审查10db27885逐字节相同。
- [恢复版CI37888154411](https://github.com/itsoso/health-llm-driven/actions/runs/37888154411)实际30/30成功，墙钟499秒（8分19秒）。相同16worker源码的不同运行也有明显波动；本轮没有证明进一步端到端提速。
- 最终主干保留16worker、原60组及严格闸，保留aggregate日志兼容、冲突拒绝、多run来源与调度数据；不保留12worker退化试验。三轮真实CI和否决记录均保留，无生产部署动作。

## 发布耗时分段取证（2026-10-09，当前增量）

- 用户要求继续优化发布速度；保留前轮已交付状态，本增量先补测量，未证明新的端到端提速，不变更应用运行时与生产授权。
- 只读复核：生产仍为`28b2471d72a3afdc7aba681bb5762dccfbae99bc`，无业务lease。历史部署日志中Pi `npm ci`实际5秒，不能把它当作362.58秒总耗时的主要来源。
- 在相同生产依赖、真实health-app身份下只读探测：版本检查0.515秒、pip check 0.866秒、全RECORD可读性检查20.764秒。随后同输入交替探测串行7.285秒、双线程5.978/5.569秒、串行3.177秒；全程零校验错误。缓存温度影响明显，双线程未证明优于串行，因此不采用，不跳过任何文件读取或JWT验收。
- 本机实际frontend依赖目录44,687个普通文件、530,375,690字节，顺序读取与复用buffer交替实验输出摘要完全一致。原读取36.379/6.216/6.793秒，候选6.856/5.506/11.632秒；没有稳定收益，因此不合入历史哈希算法变更。此实验不构成生产性能或安全验收。
- `deploy.sh`新增固定阶段名的stderr里程碑，仅输出当前Bash累计整数秒。相邻差值覆盖准备、环境封存/去激活、guard执行与验收、KB执行与验收、manifest、终态收尾；缺少最终里程碑不能推断成功。重入已终结事务可能只有部分阶段，最终成功仍以可信回执为准。没有通用命令包装器、环境/载荷输出、TTL缓存、重试或门禁削减。
- 新测试先RED（5项因缺少helper失败），实现后与完整deploy脚本回归共183项通过（92.83秒）。本增量G4/主干CI待验证；新增计时尚未用于正式生产发布，不能声明线上提速。
- 历史回执文件mtime进一步分解：started→deployment-started为4.724秒，deployment-started→completed约357.86秒，因此该轮source准备不是主要瓶颈。时间来自历史文件元数据，不是新分段日志。
- G4首轮发现新增计时测试未纳入release-invariants显式清单；已补workflow和CI契约注册，21项计时/CI契约通过。新增注册后待固定提交复审。
- G4复审固定`c51e03b47`：GO（仅代码集成）；独立21项通过、Bash语法和累计diff检查通过。另依赖/接线41项、项目`CI=true`集成3项通过。代码本轮仅本地提交；没有为了测量重启生产，也没有触发新全量远端CI。待下一次实际发布批次携带计时并获得同SHA CI及终态回执后，才用新分段数据裁决端到端优化。

## 首页新建入口与 OTA 续接（2026-10-09）

- 用户要求完成后再发一次OTA，恢复首页新建。实时Git证明`8a7d85df0`已在main，首页无条件进入chat，ChatHeader无条件显示“新建”，回调接`handleNewChat`；不重复改写已修复UI。
- 独立新鲜验证：ChatHeader 4项、首页/历史入口/engine 209项Jest通过，TypeScript通过。模拟器通过进程级DEVELOPER_DIR可用，未冒充当前候选安装界面已验收。
- 本轮已审计时改动合入main `bede48d6b0ca02e70c1c69c27f66bf54427b86ff`，CI run37893443784开始。后端仍28b2471d72a3，尚未为了OTA部署候选。
- OTA准入明确BLOCK：当前main相对固定原生包272包含RevaPcmPlayer原生Swift模块、权限文案及依赖变动，source gate拒绝；实时EAS生产runtime1.3.4原生build272/273/274/275具有三种不同fingerprint，真实`validate_builds`返回`production runtime native fingerprints differ`。更新单一NATIVE_BUILD常量不能消除cohort冲突，禁止放宽校验。
- 旧“新建”修复确实已合并，历史37721228551被CI拦住；随后37755008534在publisher中失败，无新的发布成功证据。本轮未claim、未触发vendor update、未发布OTA。已请求用户确认改走独立runtime的新扫码安装包；在回复前不变更原生版本/签名/分发方式。证据见`docs/reviews/2026-10-09-new-chat-ota-readiness.json`。
- EAS production channel实时回读：最新iOS update group为`fc8792f0-627c-4937-928c-c2a640a784f8`，update为`01a0eb0e-ec64-7a0b-bc3e-ff3bdc3deb02`，创建于2026-09-29，源码`fda864c2b7f491be79db7b4523896a499581730d`；不是本次新建修复的发布回执。不推断用户设备当前已应用哪个bundle。
- 主干候选`bede48d6b`的CI run37893443784最终30/30 job全部success。CI已满足，本轮OTA仍因source/cohort准入BLOCK；不因CI绿色越过原生边界。证据文档本地保存，待用户选择后随下一批集成，避免仅记录结果再触发重复完整CI。

## 完整HTML回复截图续接（2026-10-09）

- 截图新增问题：完整HTML文档回退为“不支持此格式预览”，同时存在未完成提示。源码定位SafeTableMarkdown仅支持严格table语法；这与旧spec明确非目标一致，不能声称主干已支持完整文档。
- 按incident + Health Harness + safety overlay执行，禁用superpowers。准入为既有观察面的安全阅读扩展，详见`docs/specs/active/2026-10-09-safe-html-document-reading.md`。HTML仅投影为原生文本，保留源码，不执行脚本/网络/CSS、不生成动作。
- 未完成状态和健康证据链单独只读调查；截图不能证明健康数据是否来自先前上下文，也不能证明服务端完成状态。禁止复制用户截图中的健康数值入fixture或用隐藏错误提示伪装修复。
- 使用现有parent run；Mobile parser/展示文件单一writer，后端scope调查只读。原OTA/native兼容阻断及待确认的原生发布方式继续有效，用户发送截图不构成同意更改分发方式。
- 第二处源码复现：准确复合句未命中closed运动scope，后续个人查询被误报nonself。新增有限今日本人推荐句式及独立HTML输出尾句；返回`今天`与空evidence_dimensions，只允许原有背景与知识工具。第三人/引用/否定/额外操作继续拒绝，原始模型输入保留HTML要求。先RED 7项失败，最终1226项scope/邻近回归通过（39.42秒）；不将fixture模型的complete当作真实HTML交付验收。
- 来源标签修复：原代码用model_generated直接断言“用户陈述”，无法证明个人事实出处。改为“上下文信息（未逐项核验）”，保留模型推断与实际检索标签，药物/写入/医生指示规则不变。配置正确测试环境后RED断言失败；修复后含医学边界/来源/选择题邻近2977项通过（20.47秒）。早期未配置数据库和一次不存在的测试路径均明确失败，不计入通过结果。
- LLM变更路径闸返回live_llm_required=false；本机检查模型凭据仅输出是否存在，未发现可用的相关provider凭据。未执行真实模型端到端复现，不宣称来源真实性或本次截图的中断原因已被确认。未读取生产健康载荷或复制其数值到fixtures。
- Mobile安全文档阅读：先RED缺模块，再实现；有序列表审查发现编号丢失，补RED（1 failed/18 passed）后保留ol默认编号、ul标记、嵌套层级及多段续文。最终四套160项Jest通过（3.793秒）、TypeScript通过；System Map和diff检查通过。未知/active/不完整/超限、含不支持表格/编号属性的文档继续整体source fallback，静态阅读不是任意浏览器页面渲染。当前候选模拟器UI与真实生成HTML仍未验收。

### 静态 HTML 与运动请求修复：固定提交独立审查

- 固定提交 `f242926f9` 独立 G4：GO，仅代码集成。独立 Mobile 141 passed、后端 81 passed，退出码均为 0；diff 检查通过。HTML 仅投影至原生 Text，未知/超限内容整体回退源码；运动句式不新增个人证据权限；来源标签不跳过医学输出校验。
- 父流程新鲜项目 CI-mode 集成 3 passed（1.45 秒）。本机最终 Mobile 160 passed 与 TypeScript、运动范围关联 1226 passed、医学输出关联 2977 passed 已记录。各组存在重叠，不累计为独立用例数。
- 真实模型、当前候选模拟器和远端精确 CI 尚未完成；不能据此宣称截图中断根因已解决或生产验收通过。现有原生 runtime/指纹 OTA 阻断继续有效，不绕过发布 Gate。

### 完整 CI 捕获来源标签消费端回归

- `fe17837c7` 已合入 main；CI `37895496999` 的 balanced-14 中真实流式编号续接两项失败。新来源标签未在 `agent_pending_choice` 的固定前缀集合中，导致 pending_choice 未持久化。保留失败记录，未部署、未取消或重跑同 SHA。
- 同类源码搜索发现 `agent_context_statement` 的固定医学拒绝文案也消费旧前缀。新增两种精确新标签兼容，旧标签继续用于历史消息；不允许任意来源前缀，不改变选项权限、整个消息哈希绑定或上下文健康边界。
- 正确环境 RED：6 failed / 132 passed，含真实 stream 两条及两个消费端的新标签。最小修复后：149 passed（6.61 秒），含 pending-choice、context-statement、真实 stream、guidance 和项目 CI-mode integration；diff 通过。固定补丁独立审查和远端验证待完成。
- 独立安全 reviewer 已补充此前后端范围无额外部署安全阻断，但必须先让修复后的目标精确 CI 通过，再走 trusted validate/readiness 和正式发布流程。Mobile/native OTA 阻断仍有效。

## 症状恢复记录与重试截图续接（2026-10-09）

- 新截图不视为此前主干红色修复推送或原生分发方式的授权。保留本地 `f11dd28ca`，生产与远端未变。
- 重试安全基线29 passed；只读生产窗口聚合发现两次无已验证写入回执告警，不读取/输出原始健康内容，不将聚合告警绑定到用户请求。复合恢复描述的写入授权仍在调查，不用放宽网关或推断病程痊愈来消除失败。
- 确认另一个独立UI缺陷：legacy done(error/interrupted，无terminalStatus)保留accepted阶段label，导致终态仍显示正在理解。RED两项失败；只在这两个分支清label，状态、恢复与重试语义不变。最终state/engine/ChatScreen 231 passed（11.446秒）、TypeScript和diff通过。不能据此声称截图新重试永久卡住或记录失败根因已解决。

## 医疗影像报告可见性只读诊断（2026-10-09）

- 用户说明历史快照来自本人 `GET /api/v1/medical-exams/me`，关键叙述在 `overall_assessment`；历史快照不等于当日实时读取。未把用户原始诊断或数值复制到证据。当前会话无本人Health API读取凭据，未声称实时数据库存在或删除已被核验。
- 代码证据：本人API依认证owner过滤并返回 `MedicalExamResponse`，该schema保留完整overall_assessment。Mobile原列表/详情及选定报告上下文保留字段；相关文件与已知生产28b2471d版本一致。
- 本地纯规则复现：`查看我的膝关节MRI报告`通过语义归属检查，`查看我的双膝关节MRI报告`及多句本人影像查询被误判nonself；语法只覆盖左/右/双侧，不覆盖双及自然复合问法。属于读前拦截，不能证明数据缺失。
- `exam_explain_service._build_explain_prompt`和调用处只传日期/类型/异常items，遗漏overall_assessment；合成纯叙述报告标记不进入prompt。health_read普通摘要截180字，/me/reports截500字；全文匹配后摘要仍可能不含匹配片段。
- Mobile `listMedicalExams`捕获请求错误返回空数组；详情从最近50条查ID，旧记录可能被显示为不存在。现有54项相关测试通过但未覆盖这些语义缺陷。
- 仓库health-query Skill未列medical-exams入口；当前其他Agent的实际工具白名单/认证未获得，不能断言其具体拦截原因。此阶段仅诊断医疗报告链，不扩大读取授权、不修改报告、不补造病史。

- 进一步症状流复现：现有pre-dispatch症状授权拒绝未进入capability blocks，误给retryable=true。最小本地补丁登记既有静态拒绝码并移除确定性拒绝的盲重试邀请，不扩大写入。新增真实流/文案6 passed、危机不回显9 passed；全404关联检查运行中。涉及agent_executor路径，live LLM gate明确required/unconfirmed，尚不具备发布条件；不将局部测试或用户新截图当作真实模型验收。
- 医疗报告补充：API/health_query_labs合成33 passed，两个真实摘要函数的合成尾部标记均被截断；独立MCP服务仅有日常指标工具，无报告专属读取。未核验其他Agent已部署工具白名单，不能把仓库配置推定为其实际权限。

- 症状恢复错误分类补丁最终全关联404 passed（328.61秒），另危机9 passed。legacy UI固定5c8923ebd独立G4 GO、30项独立测试通过。后台写入权限没有扩大；真实模型gate与发布授权仍未解除。

## Garmin复合同步指令续接

- 新截图显示设置同步时间与聊天复合请求被本人范围门拦截。只读调查区分队列入队、运动拉取完成与分析证据；不将设置刚刚同步视为本轮指令成功。
- 合成探针：单句同步佳明可通过；追加最新运动读取/跑步分析被判nonself并拒绝。继续检查第三人/否定/取消边界，未直接放宽权限。

- Garmin设置时间来自credential-status的全局last_sync_at，不证明最新运动入库。单条activity解析异常被workout_sync内部吞掉并最终只返回synced_count；实际方法合成AST验证全部失败仍返回0，上层可推进同步时间/返回success。没有实时访问用户活动，不能认定截图发生该错误。
- 同步复合语义仍需完整任务绑定：显式本人同步、当前跑步记录选择、本人时区窗口、最新一条实际running记录、同步未完成的partial结论。不能只将nonself置False或默认读7天。当前仅诊断，正向完整指令尚未修复。
- 另发现第三人复合查询会错误授权读取当前认证本人的workout（无其他user_id投射，不是跨用户DB泄露）；限制性owner检查补丁在独立回归和取消/引用边界复审中。

- owner补丁最终仅独立正向分析分句递归查归属，不删除否定词；最终3428 passed（29.16秒）。既有取消第三人后本人读正对照保留。仍发现未修的单独取消投射缺陷：本人同步后明确不要分析第三人，旧fallback仍可能读本人7天；不将本次限制性补丁宣称为全部取消语义修复。

## 2026-10-09 — Owned medical, Garmin and symptom repair candidate

User authorized all reported repairs, server deployment and one OTA. This candidate preserves prior local fixes; no write-tool description reduction is re-enabled. Admission and boundaries: `docs/specs/active/2026-10-09-owned-health-record-repair.md`.

- Medical: owned ID detail API and explicit request errors, complete assessment in explanation, canonical and legacy selected-report selectors, current/legacy product utterance compatibility, bounded complete MRI narrative read, MCP list/detail tools and CI coverage. Client summaries are discarded as evidence; stored text is not original-image verification.
- Garmin: closed sync/read/review scope, actual today's Garmin running records, isolated personal context, current job receipts distinct from activity availability, per-activity failure propagation and committed-count integrity, UTC ingestion with unknown-time limitations.
- Symptom: explicit self status observations retain the complete original recovery/residual wording; no inferred severity or illness resolution. Existing gateway, API, write receipt and failure boundaries remain active.
- Fresh local evidence: medical PostgreSQL 41 passed; focused executor PostgreSQL 7 passed; symptom PostgreSQL 921 passed (overlaps classifier regression); authorization suite 3494 passed; Garmin/reader PostgreSQL first 46 and supplemental 17 passed; Mobile 62 passed plus TypeScript; MCP 53 passed; CI-mode integration/selected/new-sync 39 passed; System Map regenerated and checked. These are distinct overlapping suites, not an additive total.
- Real-model acceptance is in progress. The symptom runner's first formal attempt failed with ValueError before case evidence; retained at `/tmp/reva-1009-symptom-status-live-frozen-01.json`, not counted as passing. Runtime source is frozen during live verification. Fixed-commit independent safety review, main exact CI, backend deployment and production acceptance are still pending.
- OTA remains separately blocked by the previously established runtime/fingerprint incompatibility. No pin bypass or legacy local publisher is used; no new native distribution has been performed.

### Final candidate review and first live acceptance

- Independent review of the initial repair found missing finite symptom/distance vocabulary and UTC-calendar prefilter errors. Commits `b31caeacf`, `57da6536a` and `5857723e1` address those cases and selected-report precedence. Independent delta review: 137 tests plus one PostgreSQL calendar counterexample passed; no gateway or write-receipt bypass.
- Garmin partial activity status now survives authentication renewal and heart-rate-only success. `fcc9d0695` passed author and independent PostgreSQL suites (67 each, overlapping). Review caught the settings home still showing a recent successful timestamp; `5a2ee191d` fixes its text and accessibility label. Author Mobile 57 and independent 49 tests passed; TypeScript passed.
- Frozen `fcc9d0695` live standard gate passed (10 actual model calls); current and legacy selected-report cases passed (3 calls each), including full assessment tail, historical isolation and stored-text caveats. Symptom acceptance passed with one verified deterministic write and zero positive-path model calls; cancellation used one actual model call and made no write. Zero-call execution is not represented as a live-model positive result.
- The direct imaging narrative live case failed: actual model proposals did not dispatch through the strict canonical keyword boundary. Three actual model calls and the failed proof are retained. This is a release blocker, not a passing selected-report result; a canonical Pi proposal repair is under test.
- The first Garmin live runner failed before provider execution because its synthetic User fixture omitted a required name. The original runner/failure metadata are retained; a corrected one-shot runner is prepared, not counted as acceptance.
- Fresh CI-mode integration plus focused-stream PostgreSQL checks: 11 passed. System Map and tracked-secret scan passed before the narrative delta. Final fixed-source live verification, independent review, exact main CI and backend release remain outstanding. Production still runs the successful `28b2471d72a3afdc7aba681bb5762dccfbae99bc`; no deployment or OTA has been attempted in this repair stage.

### Final local release candidate

- Fixed runtime `a461edf6b1f0af6c04e490c596c990647dfcfaff`: independent combined G4 **GO**, 55 tests including the three independently discovered unsupported-claim counterexamples. The rejected keyword guard is removed. Closed Garmin sync/review now traverses ordinary Pi/gateway for one sync and one current-day read, then returns verified facts and explicit limitations with zero model synthesis. It does not claim to provide a complete personal training analysis. Read-only, owner, failure, pending and receipt boundaries remain active.
- Final Garmin PostgreSQL 38 passed; fresh project CI-mode PostgreSQL integration 3 passed; System Map and secret scan passed. The independent deterministic end-to-end sample took 0.59 seconds with zero model calls, real Pi/gateway and isolated synthetic persistence; external Garmin enqueue alone was replaced by a pending test job. This does not prove production Garmin ingestion has finished and is not called a real-model positive result.
- Final revision standard live gate passed with actual API usage. Medical current/legacy selected-report and narrative, symptom and exercise-HTML samples passed at `30d064392`; independent noninterference review confirms the final delta is limited to closed Garmin handling. These samples retain their original SHA. Actual Mobile parsing accepted the complete synthetic HTML document, and parent content review found no invented personal diagnoses/readings. No current native simulator build or OTA delivery is claimed.
- Earlier failures remain evidence: direct narrative zero dispatch, generic Garmin sync filtering, missing deterministic status disclosure, unnecessary selected-report realtime search, HTML media routing/truncation, zero-record novice inference and unsupported model claims were repaired. A standard `30d064392` run also hit one 45-second provider timeout; it remains failed, not relabeled. The final standard run passed with the same bound.
- Machine evidence and explicit sample bindings: [owned health repair verification](../reviews/2026-10-09-owned-health-repair-verification.json). Local gates are complete; exact main CI and trusted backend release are next. The native runtime/fingerprint OTA blocker remains; no incompatible pin or legacy publisher is used.

### 精确 CI 失败与修复（2026-10-09）

- `3bcce550c` 的 CI `37909184530` 阻断：新增本人报告详情路由漏同步两端生成类型；体检续问测试期望的可信入口意图标签被清理。未部署该候选。
- `d1dd58cab` 同步两端 OpenAPI 类型，并由服务端补入固定只读 `exam_abnormal_review` 标签；不恢复客户端摘要或 `feedback_intent`。原失败断言保持不变，新增恶意标签隔离断言。
- API 生成一致性、Mobile/Web TypeScript 均通过；作者 PostgreSQL 82 passed，独立安全复核 82 passed / G4 GO。新旧所选报告真实模型补验及下一候选精确 CI 尚待完成。
- `d1dd58cab` legacy 实模机器检查通过，但人工 G4 内容审阅 **BLOCK**：缺年龄/家族史仍下调具体遗传疾病可能性，且将一般运动目标放入无适用条件的个人行动清单。保留 `/tmp/reva-1009-selected-d1dd58cab` 原始证据；不能将机器通过当作医学内容通过。返回实现收紧所选报告解读约束，发布未执行。

- `6062f1cfb` 收紧所选报告内容边界：未知不当阴性、不据单项指标推个体病因概率、人群目标不变个人运动或减重处方。作者 PostgreSQL 82 passed、独立 82 passed / 代码 G4 GO；最终 CI-mode PostgreSQL 基础集成 3 passed。
- 新目录 `/tmp/reva-1009-selected-evidence-limits` 三份单次真实模型验收（legacy/current/variant）各 24 项机器检查通过，各 3 次真实 API，共 9 次，源码绑定 `6062f1cfb` 且前后哈希不变，无重试。独立逐篇人工内容 GO，原机器 proof 保持 pending_content_review，裁决独立保存并绑定内容与 proof 哈希。旧 BLOCK 证据不覆盖。样本通过不等同线上用户验收。
- 下一步：证据提交后的精确 main CI → Trusted Release validate → 服务端部署和健康回执。OTA 原生 cohort 不兼容阻断仍在；不改 fingerprint pin 或借旧入口发布。

### 服务端发布回执（2026-10-09）

- 当前 main 发布候选 `993908ddf6c15a3cfff98c4e399e9ae592146900`：精确 CI `37911602321` 成功；Trusted Release validate `37912566007` 成功；backend `37913658754` 成功。
- 服务器持久回执 `SUCCEEDED`，SHA256 `0739415f09217525923057c76f112a49f238c510baefd91eaac08bbb8e72bc45`；生产运行 HEAD 同候选，backend/frontend/Celery worker/beat 全部 active，无遗留业务发布锁。公开 health HTTP 200；所选本人报告详情未认证 HTTP 401（只验证鉴权边界，未读取真实用户健康数据）。
- `/tmp/reva-release-993908dd-final.json` 保存本轮终态摘要。此发布后记录暂留本地，避免更改已经发布且 CI 绿色的 main 候选。
- 服务端部署完成；线上真实用户 Garmin 同步、本人医疗数据和当前移动 UI 仍未做用户态验收，不能以合成验收或 health 200 冒充。
- OTA 未发布：`1.3.4` production 原生 cohort fingerprint 不一致且存在原生输入变化。新原生 runtime/安装包交付授权问题仍待用户答复；未修改固定原生基线，未调用 vendor update，未触发失败 OTA 重试。

### 新原生 TestFlight 发布授权（2026-10-09）

- 用户明确要求“发布新的testflight版本”并“授权发布”，解除此前新原生交付待授权状态。本轮范围是 production TestFlight 新包，不包含正式 App Review/公开商店提交。
- 新鲜核验：origin/main 与生产仍为 `993908ddf`，后端回执 SUCCEEDED，无业务 lease；EAS 最新 production STORE iOS 构建为 1.3.4 (275)，近期列表无运行中构建。
- 最小配置变更：appVersion `1.3.4 → 1.3.5`，runtime 仍由 appVersion 派生，新原生 cohort 避免旧 1.3.4 指纹混用。production autoIncrement 保持，不手工预测/占用 build number；不改旧 OTA baseline 常量。
- 原主目录仍有其他会话 WIP 和分叉，保持原样；本轮只在既有 `health-prompt-optimization` 工作树继续。
- Expo production 配置已解析验证 1.3.5、appVersion runtime policy、原 bundle identifier；锁定发布 CLI 的安全回补及 3 项兼容测试通过。候选 CI、独立 G4、构建上传、Apple processing 和同包验收分别记证，不把上传等同测试可用。
- 本地新鲜验证：ChatHeader 4 passed，Mobile TypeScript通过；CI-mode基础集成与发布契约合计95 passed（本次无DB逻辑变化，SQLite快速层；既有PG证据不冒充新运行）；独立发布契约253 passed，production Expo配置复核，G4 GO。仅版本配置变化，不改变服务端、模型提示、权限或数据读取范围。
