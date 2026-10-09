# 按发布目标验证与制品复用

| 字段 | 值 |
| --- | --- |
| 状态 | validated |
| 当前阶段 | S7 发布后验证 |

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
