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
- 首个1.3.5候选 `1033a3099` CI `37921723275` 在 Mobile app-config 旧版本精确断言失败（仍期望1.3.4）。保持失败记录，未启动构建。更新版本契约测试名称/精确期望至1.3.5，保留appVersion runtime与production能力边界断言；不修改历史OTA baseline fixtures。
- 修正断言后 app-config/ChatHeader 合计43 passed；独立app-config 39 passed，版本源码哈希不变、G4 GO沿用。
- 1033候选后续balanced-09另暴露验收模板app_version旧值；最小同步 `real-device-acceptance.template.json` 至1.3.5，全部占位符及false检查项原样保留，未声明设备验收。完整release-pack回归64 passed。ASC已由用户完成登录并回读最新仍为1.3.4(275)，无1.3.5新包；后台可用于后续独立处理/分发核验。

### TestFlight 1.3.5 (276) 与服务端发布完成（2026-10-09）

- 精确 main `7fe06d8b34750b6bd56db8d5ec45d1aee705b02e` 完整 CI `37922798912` 成功；该模板文档候选的自动轻量 CI 不作为完整验证。Trusted validate `37923921378` 与 release `37924699485` 均成功。GitHub 查询有网络 EOF，原运行未重建；首次 validate CLI 在 GET 工作流阶段失败，确认未 dispatch 后使用官方 API 触发一次。
- 服务端同 SHA 持久 `SUCCEEDED`，回执 SHA256 `146912e8801f90df21114139d96406028316b907ab116f1a7bf2861fb00b23ce`；backend/frontend/Celery worker/beat active，业务 lease 已释放，公网 health HTTP 200。生产真实用户数据未读取或写入。
- EAS 唯一构建 `09719eb6-2887-4100-9ccb-6533fd9d71ed`：1.3.5 (276)，IOS / STORE / production，精确源码相同，FINISHED。构建创建 11:38:04 UTC、完成 11:44:58 UTC（约 6 分 55 秒）；不据单次数据宣称长尾性能改善。
- 唯一 submission `81028957-cf20-4904-8f3d-a674d53e8f81` 上传成功。ASC build `d7e8ad8c-72d8-4854-bc03-9058085d7f9f` 的上传状态为“完成”，确切 1.3.5 (276) 已绑定既有 Team (Expo) 与“内部测试”两个内部组，测试说明保存成功。没有增加新测试员或提交 App Review。
- 下载精确 IPA 核验版本、build、bundle `life.executor.health`、runtime 1.3.5 与 production channel；codesign deep/strict 校验通过，商店 profile 不可调试、无设备列表。IPA SHA256 `23e51c8d0455d8bfceec5f4d6fe2e46816dadef2a03251f5c33133685e607761`。第一次 urllib 下载 HTTP 403，curl 读取同一 vendor 制品成功，未重建或重上传。
- 本机证据 `/tmp/reva-testflight-135-final.json`、`/tmp/reva-testflight-135-upload.log`、`/tmp/reva-testflight-135-276-available.jpg`。本次未做 276 真机安装或用户态端到端验收，不能将签名/上传/分组替代设备验证；未送审、未发 OTA。新原生 runtime 已交付，不改旧 OTA baseline 绕过兼容性闸。
- 本节保留本地作为发布后回执，不推进已发布的 main。原主目录及其他会话工作未修改。

### 发布速度实测与第一批优化（2026-10-09）

- 用户要求同时分析并改进后端部署和 TestFlight 发布。沿用当前 ledger；保留上述 276 发布回执及原主目录的其他会话改动。
- 基线：[机器可读耗时](../reviews/2026-10-09-release-latency-baseline.json)。run 37924699485 共 930 秒：backend 385 秒、iOS job 505 秒、TestFlight job 368 秒；两条路径已并行，不能再把“并行后端与构建”当新优化。构建结束后的 upload claim 166 秒、实际重验/上传 165 秒是当前关键路径。
- 后端 deploy.sh guard 段 152 秒；日志证明 Python 依赖已复用、Pi 安装约 5 秒。新增独立 remote_* 时钟检查点细分停止 writer、checkout、依赖、迁移、schema 和服务重启；固定阶段名和秒数仅写 stderr，原失败链与锁保持，不声称计时本身缩短部署。
- 接受：ios-build/testflight 两个独立 npm ci 根固定并发 2，均使用锁文件、ignore-scripts、干净 runner 与既有环境清理；必须 join 两项且全部成功才做安全补丁/领取权限/接触 vendor 凭据。无跨运行缓存、无新权限、无自动重试。
- 真实本机安装对照：同锁文件、每组新缓存，serial 126.27 秒、parallel 83.90 秒；仅一个 macOS/Node25 样本，不等同 Linux/Node22 正式 runner，不宣称全发布或 P95 改善。下一次正常授权发布以相同步骤耗时验证。
- 拒绝：历史备份双线程哈希。冷/暖数据差异大；ABBA 串行 29.33/21.61 秒，并行 22.14/29.03 秒，没有稳定收益，已撤回运行代码和对应实验测试。所有原始摘要检查通过；实验中新增的“两个任务都必须开始”测试也暴露 executor.map 可能取消尚未开始任务，此失败记录保留，不计入通过结果。生产源/回执/缓存未修改，也未清除 OS page cache。
- 后续优先级：P1 为 bootstrap 持久公钥复用链 O(N²) 的单次完整图验证，必须另做循环/断链/授权改变/归档篡改反例和固定提交独立评审；P2 根据新增 guard 分段实测，优化实际耗时函数，保留停服、迁移、schema 与稳定窗口；P3 评估构建产物准备与同包上传衔接，继续保持失败不重放。暂不引入共享特权缓存或跳过完整字节验证。
- 停止条件：任一依赖失败仍能进入 patch/claim、凭据提前可见、原回执/失败语义变化、或真实耗时无稳定改善，均撤回相应优化。正式效果待绿色候选下一次发布回执；不为计时重复发 TestFlight 包。

- 第一批交付终态：固定提交 `50a2352fca678ba29b6d22af8a39c558ada9a479` 已合入 main，完整 CI `37928153785` success；作者最终发布回归345 passed，独立固定提交89 passed / G4 GO，System Map、密钥扫描和shell语法通过。发布后记录留本地，不另推main。本轮没有新建TestFlight或重新部署服务端；workflow优化已在main，新增后端计时将在下一次正常部署执行，生产端到端收益尚未测量。

## 续轮：餐食识别等待投诉（2026-10-09）

- 只读生产分段证据：当日一条 diet_photo 成功回合总耗时 57.69 秒，pre_llm 9.02 秒，模型处理 47.25 秒；相邻 Vision 调用 7.71 秒。持久化终态含一个写回执和一张卡片。时间邻近及链路类型支持关联，尚待用户确认是否正是投诉回合；不同图片不能作为版本性能对照。
- 实际 Vision 使用 qwen3.8-flash，保留 compact JSON 和关闭 thinking；没有恢复被否决的写工具说明精简。源码确认已持久化的餐食卡片仅合入 done，导致后续模型回复延迟挡住卡片。
- 最小改动：在 agent_start 后、任何后续模型调用前，仅流式返回本轮 verified diet_record 回执匹配且 recorded=true 的卡片；保留原模型、提示词、识别、校准、写入、确认与最终回复。补齐 write_verified_ms/first_card_ms 便于后续测量。不将草稿、未核验卡片或部分回复当作保存成功。
- RED：真实保存入口的回归在模型开始时断言尚无卡片，失败；GREEN：卡片先返回，后续拒绝写入仍保留同一条原始记录。测试注入未验证卡片及同 ID 草稿，均不得提前发布。第一轮后端173项、Mobile流协议37项通过。最终顺序及独立 coverage 文件重验中，标准 live gate 与 G4 待验；无生产提速或发布声明。
- 另一 checkout 的份量修正回执补丁与视觉工作保持不动。本轮只解决结果展示被长回复阻塞，未宣称降低 Vision 本身或整体模型生成时延。
- 固定 dc8d9109a 独立 G4 NO-GO：后续失败终态会令 Mobile 清除已验证保存卡片，历史恢复也隐藏。独立反例复现；未推送或部署此候选。
- 追加最小 Mobile 修复：在 failed 等非完整回复中，只保留匹配 verified diet_record 回执且 recorded=true 的餐食卡。实时收尾和历史恢复复用同一过滤函数，回复失败状态不改，草稿/无回执/不匹配卡片仍隐藏；仅返回服务器已持久化 messageId 的终态。RED 1 failed/3 passed，GREEN三套181 passed，TypeScript通过；重复卡补验中。
- 后端最终173 passed、CI=true项目集成3 passed、System Map与秘密扫描通过；标准真实模型回归10次API、0失败，源文件哈希与固定后端提交一致，证据 /tmp/reva-diet-stream-live-result.json。该标准回归不等于真实用户照片的成对时延或质量评估。新固定提交待独立复审及远端CI，尚未部署/OTA。
- e4ac5c966 独立G4 GO：固定快照Mobile211 passed及无回执/错误资源类型/未持久化/缺messageId四项额外边界通过；已合入main，CI37930959574运行。后端修复不改变任何模型输入输出；Mobile失败时仅保留持久化回执卡。
- OTA准备发现固定基线仍为1.3.4，不能直接发布1.3.5 JS。按本会话已核验TestFlight276构建回执升级三处绑定：runtime1.3.5、native SHA7fe06d8b34750b6bd56db8d5ec45d1aee705b02e、build09719eb6-2887-4100-9ccb-6533fd9d71ed。已保存EAS回执FINISHED/STORE/production、原生指纹11aca32700f896b9e3f46e8587dc052de72090dd，IPA/Apple分发证据见前文；本次本机EAS只读刷新认证不可用，发布器仍须实时校验完整cohort和指纹。不扩大OTA路径白名单，不删除旧版本历史，不更改渠道映射。
- 基线绑定RED复现，旧常量测试更新后121项通过。新提交须独立复审与新精确CI，再做后端及OTA validate/publish；不能把此前绿CI或本地构建回执替代新发布Gate。

### 本轮发布结果：收尾失败，OTA未执行

- 最终候选 e3210b1161f76944733b6522e0ff21695858614c；独立G4 GO；完整CI37931373747的30项全部成功；validate37932502649成功；规范staging和bootstrap授权轮换完成，保留旧安装与回执。
- 后端工作流37933398517失败，原始持久回执state=NEEDS_OPERATOR，SHA256=e60e31e742f5cc6d36d9e4578119e4c112bb81bf3d7761d708b6cd083c7f94d4。禁止重发同SHA、覆写回执或按锁空闲推断成功。
- 部署日志guard两次健康评分60/60、manifest通过；最终LAYA_VERIFIED后、下一次verify_deployment打印前失败，收敛到进程/去激活证明阶段（也可能SSH故障，缺少具体错误码）。自动恢复结果ROLLBACK_OK，runtime_state=candidate-retained；恢复保留e321代码，运行环境flag=false。当前四服务active、健康200，原业务lease已释放。这些不是部署成功或用户验收证据。
- 只读Systemd时间线：13:03:04UTC首次重启完成，13:04:27UTC开始恢复停机，13:04:45UTC恢复完成；期间未观察到Main process exited或自动重启事件。13:04:24UTC有route=pi回合结束（8.52秒）。PiKernelSession的环境白名单不含HEALTH_EVIDENCE_RUNTIME_ENABLED，而证明要求整个cgroup全部进程唯一flag=false：存在可复现代码冲突，时间相关性支持但尚无当时PID级证据证明唯一根因。
- 独立恢复边界调查：现有contained retirement仅适用checkout前、prior终态与原lease/stage保留；本案不匹配。runtime finalize不能代替失败terminal gate，不能把NEEDS_OPERATOR改为SUCCEEDED。未调用任何恢复变更入口，未发OTA、未重建TestFlight。下一步需对进程证明冲突及本阶段受审恢复路径分别修复验证，保留原失败审计。
- 本次分段：remote guard停写2秒，checkout累计113秒，依赖累计176秒，迁移177秒，schema180秒，服务重启180秒；manifest总337秒。授权轮换历史校验读取约6.29GB。不得将本次发布称为提速成功。


## 饮食识别 4～5 秒体验：同图短字段复测

- 固定 `qwen3.8-flash`、同一组图片字节、temperature=0.1、max_tokens=2000 与关闭 thinking；不改模型、分辨率、写入工具说明、营养规则或权限。三张已授权餐食照片，加标签、订单、非食物、界面合成样本；AB/BA 交替，两个独立时间轮次、每轮两遍、共56调用。没有写入生产健康记录。
- 第一候选在完整提示后追加单字母映射说明，输入反增113 Token、整体P50 2378→2885ms，否决。首轮严格JSON校验将一个生产可解析的代码块计为失败，保留原报告；第二候选重新全量运行并统一使用生产解析，未篡改原分数。
- 第二候选只在完整规则和JSON示例中替换八个冗长字段名，不加第二份schema；服务端仅还原顶层与food字段，不修改字符串或任意嵌套元数据，兼容旧长字段响应，混合冲突字段拒绝并返回失败。API结果保持原契约。
- 两轮各自改善餐食照片均值：4653→3108ms、4331→3231ms。合并真实照片P50 4334→2909ms、样本P95 6497→4780ms；全部样本P50 3578→2682ms、样本P95 6662→4508ms。每调用输入少19 Token，平均输出191.46→165.75（约13.43%）；未声称大幅压缩输入。
- 56次API均成功、冻结质量契约均通过；仅证明这些样本的字段/数量/品名/标签值/订单数量/未知值及未授权完成措辞，不能证明临床营养真值、全面语义不退化或线上端到端P95。聚合无健康原文证据：`docs/reviews/2026-10-09-food-wire-replay.json`。
- RED 7 failed/4 passed；实现后识别/权限/实际executor/benchmark回归262 passed，额外冲突消费端回归与CI-mode集成继续验证。System Map通过。停止条件为新质量失败、同图P50或P95恶化、成本增加或冲突字段可记录；发布后仍须核对首卡、保存和总耗时，必要时回滚。
- Pi标志修复固定`f8a1c3372`独立G4 GO：38 Python +26真实Node；新失败收尾协议`2dd7c2420`独立审查发现撤权前置死环，BLOCK并修复中。旧`e321`失败回执保持原样；本轮尚未push、部署或发布OTA。

- 固定`1720a749b`独立G4 GO：264项回归通过；额外穷举256种长短字段混合组合完全等价、8种冲突均拒绝；56条真实指标与提示哈希重算吻合。父方补充边界44 passed、CI-mode集成3 passed。标准真实模型回归10次API/0失败、三个运行源码hash运行前后一致，证据`/tmp/reva-food-wire-runtime-live-result.json`；这是通用交互回归，不替代照片56次对照或线上首卡验收。

- `2dd7c2420`的两项BLOCK已修补待重审：通用revoke仍拒绝NEEDS_OPERATOR，独立closure在durable intent和重复证据后精确撤销旧双身份/旧loopback私钥，失败留intent且不给completion/receipt；补齐candidate effective units、network guard与Laya安装/服务/候选证明。437项回归通过（含真实install→NEEDS_OPERATOR→close及写失败/后置偏离）；原GH失败run终态由operator独立fresh核验。未运行生产收尾或推送。

- `0022cdb0c2376ecd49daab219721901b34c814a2`独立G4 GO（394项），已快进推送main；精确完整CI `37938611767` 30项成功，job-span507秒；Trusted validate `37939749443`成功，canonical staging及生产GitHub relay/TLS检查通过。
- 生产只读retirement inspect被真实兼容项阻断，未传evidence digest、未创建intent、未撤权、未部署/OTA。安全诊断确认 `ProofError: effective drop-in inventory differs`，`contained_recovery_proof.py:735`；三个业务unit有已治理的末位`zzzz-reva-vision-model.conf`，旧基础unit proof只认原三个drop-in。原失败receipt及授权保持不变。
- 下一修复需完整核验视觉overlay文件/真实环境源/进程模型/历史来源绑定后，仅将这一个已证明的末位DropInPaths作retirement私有只读投影；其他属性原样、未知/乱序/重复/篡改均阻断，并归档真实列表和overlay证明。方向审查GO不等于实现G4；修复与新精确CI仍待完成。

- 父方单独调用相同canonical candidate_laya只读函数，生产generation/来源回执/导出源码/账户/service/401/synthetic inference真实通过；没有传evidence digest或写closure，不替代完整retirement证明。日志`/tmp/reva-retained-laya-diagnostic.log`仅含passed。
- vision overlay私有适配已实现待固定G4：493项相关测试通过；真实列表恰为原三项+唯一末位model路径，独立验证文件/环境/进程model及完整历史来源，只投影DropInPaths，其他属性原样；前后复验及首次rotate实时复验，未来历史仅验证归档。CLI仅输出固定stage、白名单异常类与retry_allowed=false，禁止原始异常/argv/健康载荷回显。尚未执行生产新适配。

- `5f8051576` overlay修复497项通过；合并另会话纯规划文档后候选`fdeb4ceb6e66d5633891a44398b97aa3fbba683a`独立G4 GO（454+8），精确CI`37942968544`全部30项成功，Trusted validate`37944086974`成功；canonical staging通过。未改变已通过10次真实API回归的应用源码哈希。
- 该候选生产readonly inspect通过Vision配置阶段，在`application_probes`以CalledProcessError阻断；无intent、无撤权、无新部署/OTA。独立canonical child安全诊断定位`verify_runtime_only_kb_contract.py:353`，要求active/reviewed目标集合不满足；schema与前置来源校验已通过。源码证实rollback的candidate-retained路径同样先quarantine后commit/finalize，staged active profile与合法隔离状态矛盾，不能因此认定KB损坏。
- 正在实施独立`ROLLBACK_QUARANTINED`严格证明：完整sealed ID/type/review/artifact、全部archived、generic目标不可见/runtime全可见集合空、flag=false、原workspace与完整SHA/审计/时间窗绑定；保留schema、advisory lock和projection正负例。不写DB修复、不改guard、不catch staged失败fallback。projection使用savepoint sentinel后回滚，应称无持久业务写入而非零SQL写。新固定G4、PostgreSQL证据与CI待完成。
- 原canonical child生产聚合诊断：target/matched/archived/reviewed/correct_type均11，证明不是缺失行；仍由原staged在353行拒绝。只输出计数与源码栈，日志`/tmp/reva-retained-kb-count-diagnostic.log`；不替代sealed artifact、审计来源及完整不可服务证明。新的真实PostgreSQL回归已复现原staged失败，专用隔离证明验证中。
- `1a7a4c86296f246daca18caefa4e29391b0eed9b` 独立G4 GO（479零skip含13真实PG，另4 PG负例），精确CI`37946610730`全部30项成功，validate`37947768429`及canonical staging成功。首次readonly inspect为ProofError（阶段标签停在vision_overlay），原始失败保留；后续独立running_services_snapshot通过，旧Pi缺flag是源码可证风险但非该次确证根因。
- 完整canonical只读诊断继续通过quarantine/application和服务前后稳定性证明，随后在`validate_live_snapshot:1459`以`invalid archived service readiness`拒绝。真实systemd socket active/running/Result=success，MainPID/NRestarts属性不存在（show空串）；归档验证误把socket当service要求这两项数字。新增真实socket shape回归及最小契约修复中。无intent、无撤权、无部署/OTA，所有旧失败保留。

## 实际交付进展（2026-10-10）

- `3a75b0567adec01b585260b562cd397194293240` 独立G4 GO，498零skip（含13真实PG）；精确CI`37950049412`全部30项成功，validate`37951214267`成功。canonical生产完整inspect通过，独立closure终态`CLOSED_RETAINED_CANDIDATE_FAILURE`及bootstrap轮换完成；旧e321失败回执哈希及原锁inode保持。回执只保存在root-only文件，未输出秘密。
- 后端实际部署`37954997061` completed/success；持久回执3a75 `SUCCEEDED`，live HEAD一致、四服务active、health200/healthy、业务lease不存在。三个真实模型验收源码hash与线上文件一致，私有证据`/tmp/reva-food-wire-deployed-check.json`。这确认提速实现已部署，不等于手机端到端时延验收。
- OTA validate`37956709983`在无凭据publisher_context阻断，reason=`publisher_path_untrusted`。规范checkout、固定Node硬化、锁定依赖安装成功；preflight失败，publish/audit步骤跳过，没有OTA claim或上传。不重发该失败run；正在定位具体路径元数据，禁止放宽root-owned/无group-write/无symlink约束。当前TestFlight基线仍1.3.5(276)，本轮不重建原生包。
- OTA 路径诊断补充：锁定 EAS/Expo tar SHA512 与 bin 元数据核验通过，但 npm 10.9.2 的 bin-links 会按进程 umask 重设可执行文件权限，因此不能从 tar 模式排除安装阶段问题；尚无 hosted runner 的具体违规对象证据。新增仅固定资源角色、祖先层级及 owner/writable/kind/hardlink 枚举的无凭据诊断，保留所有原准入约束；不做推测性权限修复。后台新鲜只读复验仍为3a75 SUCCEEDED、四服务active、health200。
- 诊断提交 d5b797d（dossier后继f16ab6486）独立G4 GO，144项通过；精确CI37958088141保留失败记录。release-invariants命中新增fixture跨平台缺陷：Linux外部临时目录01777先于故意违规文件被拒绝。5fb1c68a仅修fixture外部祖先模拟，增加Linux式参数RED9失败，独立153通过；生产secure不变。另balanced-13暴露5项佳明读取测试跨午夜失败，待分别定位修复。未触发OTA或新后端部署，生产仍3a75。
- 93953a3d8仅修佳明测试时钟：实时now−30分钟在北京时间午夜后落入昨日，原fixture却标今天；生产按start_time筛选正确。冻结ExecutionContext.now至合成日中午并从同一上下文派生记录，真实午夜RED19失败/21通过、GREEN40通过，未改生产日期或权限逻辑。与5fb Linux夹具修复一起等待新精确CI；原失败不重跑、不覆盖。
- d7ddaefdf精确完整CI37959159002全部30项成功；无凭据OTA validate37960150375明确诊断publisher/ancestor_depth=2/writable，即canonical source根目录组或其他用户可写。没有claim/上传/新后端部署。按实际生产者修复root Git/npm子进程的创建umask，禁止放宽secure或递归修复未知目录；原失败回执保留。
- 已用真实Git首次建库复现：继承umask0002时canonical source创建为0775，原校验正确拒绝。修复在root Git shell及各锁定依赖生产者root子shell内设置022，再exec固定argv；不chmod/chown现有树。作者RED真实目录模式失败，GREEN140通过，覆盖source/.git/config与依赖目录/普通文件/bin模式。待固定独立G4、新CI及hosted预检。
- f504f0d0c精确完整CI37960716054全部30项成功，canonical staging完成；OTA validate37961746754仍在publisher祖先2 writable阻断，证明仅umask不足。没有轮换生产授权、后端部署或OTA claim。后续改为拒绝已有路径的fresh-source创建：仅对新空目录通过dirfd规范继承default ACL和0755，并记录固定阶段元数据。default ACL仍为待hosted证实机制，不能将本地umask复现当作已解决根因。
- c6f8af755将source改为parent-dirfd下独占新建空目录，以NOFOLLOW/inode/empty绑定，仅该新目录清除default ACL并设0755；已有目录/链接/不安全parent及非ENODATA错误均拒绝。创建、checkout后、依赖后输出固定安全元数据，secure未改。作者153通过/1 mac明确skip；真实Linux ACL测试在Ubuntu必须执行，尚未据本机结果宣称已验证ACL机制。
