# 体检解读返回与继续讨论回归

| 字段 | 值 |
| --- | --- |
| 当前阶段 | G3/G4 本地验证完成，未部署 |
| 状态 | building |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Run | `docs/_generated/harness-runs/5b5be9f937ce.jsonl`（本地） |

## G1 / G2

裁决: PASS。修复既有体检解读页面返回主会话和只读继续解读能力，不增加自主诊断、
开药或健康记录写权限。主对象为既有体检记录和会话上下文，认证后端仍为数据真源。
用户截图中的“最近一周”读取拒绝一并核对既有修复，不扩大部署或发布权限。

## S5 范围

- Mobile：体检解读页面退出、主屏会话导航及上下文传递，先补失败测试。
- Backend：复现内置提示词被临床来源护栏误拦截，保留真实临床依据复合写操作的拒绝。
- 保留其他任务的前端发布恢复档案与 Android 构建现场，不修改生产健康数据。
- 外部 TDD/verification 能力未在本会话提供；使用仓库 RED/GREEN 与新鲜验证，
  不调用禁用的 superpowers。

## G3 / G4

- UI 根因：原页面仅成功时声明原生 header，加载/失败没有退出；讨论按钮 push
  主会话，保留上层 modal。改为固定页头覆盖各状态，并仅此入口 opt-in dismissTo，
  携带相同提示词、报告上下文、badge 和新会话参数。RED 6 failed/1 passed；
  三组 Mobile 回归 29 passed，TypeScript exit 0；未做模拟器原生验收。
- Backend 复现内置提示词为 `unresolved_clinician_action`：名词“复查安排”加
  “向医生确认的问题”误入动作拒绝。局部只读问诊问题准备分类不覆盖医生转述、
  临床依据变更或独立写动作；真实写权限仍由原 capability policy 裁决。
- 先测出现 5 failed/19 passed：四个只读用例失败；第五个是测试错误要求原有
  zero-tool clinician_context 必须命名为 ambiguous，修正为验证原零工具安全语义，
  未改变产品分类来迎合测试。组合回归 1719 passed，包含完整 run_stream 的
  上下文、输出与无写入回执验证，以及第三张截图“最近一周”的现有范围回归。
- 运行时测试使用受控模型 stub 和合成数据，不是实际模型医疗答案质量证明。
  没有 schema/API 变更，不把 SQLite 用作生产数据库语义证据。
- LLM change gate passed / live_required=false；结构、地图、秘密扫描通过。
  固定提交独立安全审查待执行；当前不宣称全部发布闸通过。

### 独立复审回退

固定 `017d2aa0e` 相对 `1bdd64af1` 的独立 G4 NO-GO：问题清单之后的命令式
“把复查安排在明天上午八点”和含零宽字符的修改命令可能被新只读例外接受。
写工具能力探针仍拒绝，不声称发生数据库越权；但丢失确定性零工具拒绝本身即阻断。
新增前缀/后缀反例先得到 6 failed/4 passed；修复将 deny-only 动作规范化扫描扩展到
所有分句，并把名词例外限制到医生对象之前、同一问题准备分句的明确列表位置。
需完整重跑与新固定提交复审，不沿用旧 GO。保留原 NO-GO 与失败证据。

首轮护栏覆盖率 97%（616 passed）；Ruff 最初报三处 import 排序问题，机械修复后通过。
本机有 iOS 26.5 模拟器，但默认 xcrun 指向 CommandLineTools；仅以局部
DEVELOPER_DIR 确认可用，未改全局配置。已安装应用不是本轮候选，未把它作为验收证明。

第二轮固定 `bbe5299a5` G4 仍为 NO-GO：同分句的“复查安排在明天”缺少名词终止
验证；跨换行的修改动作未被逐分句扫描捕获。新增反例 RED 7 failed/12 passed。
再修复采用仅拒绝用途的跨分句字母数字规范化检查，并要求“复查安排”后立即为
列表连接词/分隔符；原始同分句位置和写工具权限检查不变。新完整回归与复审待回读。

### 最终本地验证与审查

- 代码候选 `9bec52f4401685afc0d3200bd61df98475ff8ce8` 相对 `1bdd64af1`，
  指定六文件独立 G4 GO。审查者额外验证 650 个既有动作词前缀/后缀/混淆变体
  均维持拒绝或零工具上下文，4 个正常问题准备请求可继续解读，12 个模型提议写操作
  全部拒绝；独立 Backend 47 passed、Mobile 7 passed。
- 最终后端组合 1738 passed（`/tmp/reva-exam-review2-green.log`）；护栏覆盖率
  97%，635 passed（`/tmp/reva-exam-reviewed-coverage.log`）；Mobile 三组 29 passed，
  TypeScript exit 0。Ruff、结构/地图、秘密扫描与 diff 检查通过。
- 离线 LLM Gate invariants 12/12、health_agent_core 50/50、轨迹 12/12、goldens
  9/9；路径闸 live_required=false，没有伪造 live confirmation 或调用生产模型。
- 原始内置提示词及其安全声明未删除；只修复导航和确定性意图误判。
  “最近一周”截图原话在既有范围回归中通过，不证明线上目标 revision 已更新。
- 本次没有 push、后端部署、OTA、原生上传或生产用户数据操作；不复用其他线程
  发布权限。完整精确 CI、真实模拟器候选导航与发布后回答质量验收仍属后续 Gate。

## G5 / G6

未部署，未宣称线上或模拟器验收完成。

### 经授权的合并与发布续接

用户明确授权合并分叉代码、协调旧发布受控收尾，随后部署后端和 production OTA。
固定合并提交 `900ecdb20640edd4f47b3981226b98973be367de` 保留本地体检修复与远端
`3250d770f73146091ab4b86c05dba033e645ff27`；地图提示及其测试统一为远端已测试文案。
其他任务未提交的 frontend-publisher-recovery 档案保持原样，不纳入此次提交。

- 合并后 Backend 1917 passed；Mobile 35 passed；TypeScript、结构地图、秘密扫描通过。
- 体检增量独立 G4 GO：五个代码/测试文件与原受审候选同字节；独立 Backend 1738、
  Mobile 29、decision routing 10 均通过。另以合成 Laya provider 和真实 run_stream
  验证 decision_mode=on 的上下文、质量下限、无写回执/用药卡，1 passed。
- 恢复代码独立 G4 GO：固定 `3250d770f` 相对 `ba861b623` 的六文件在合并候选
  同字节；133 项恢复/安装器和 203 项 bootstrap/server 测试通过。此 GO 不等于
  生产证据匹配、发布或 PostgreSQL 业务验证通过。
- 生产只读检查仍为 `05b6e4d396084103975c43e4a5fc4d044d8e66da`，backend/worker/beat
  active、restart count 0。旧发布 lease 保留；未启动新的生产操作。
- 当前全量发布不变量测试与远端基线 CI 尚在运行；合并候选精确 CI 尚未触发。
  `run-all-tests.sh --ci` 不受该脚本支持（exit 2），不算验证；已改用 CI workflow
  中原样的 release-invariants 集成命令。没有关闭测试或放宽闸。
- OTA 本地历史锚点为 runtime 1.3.3，当前配置为 1.3.4；必须核对已分发原生候选，
  不以覆盖 runtime 或 OTA 推送替代原生权限/版本更新。

续接验证：CI 原样 release-invariants 命令 1257 passed、8 skipped、84 subtests
passed（395.90 秒，exit 0）。前端 411 passed，类型与 lint 无错误。快捷 Mobile
全量并行运行未结束，已中断；串行全量同样未结束，已中断，均不计通过。按现有
CI workflow 原样隔离四个 stateful 套件后，309 主套件加四组隔离套件全部通过，
合计 313 suites、3049 passed、1 skipped，各进程 exit 0；未改测试或跳过原 CI 套件。

基线 `3250d770f` CI `35975564110` completed/success 后，已推送
`a6b6e0e41b07caad138fcc66ab3aaf34660c8ca7`；其精确 CI `35977649858` 仍在运行。
EAS 只读查询最新商店 build 为 1.3.3 (271)，未发现可分发的 1.3.4；既有1.3.4
本地包因 development entitlement 未发布，不冒充 OTA 兼容原生基础。

发布所有权核对发现另一 `3250d770f/recover_contained_services.py` 进程，其后已退出，
未见 `ba861b623` 新 closure audit；已向关联 Laya 任务发只读协调通知，请其报告终态，
禁止并发重启旧恢复或旧 SHA 发布。当前任务尚未执行任何生产 mutation。

精确候选 CI `35977649858` 与 validate-only `35979933321` 已全部成功。
累积 operator/closure/rotate（含固定 Node 链接依赖）独立 G4 GO，456 passed、
84 subtests passed。因候选包含既有 Laya 迁移，发布 overlay 加入 database；在新建的
本地隔离 PostgreSQL cluster（仅 Unix socket、专用 test 数据库）验证 control/consent
15 passed，并正常停止实例；未触及生产 DB。迁移/ORM 与已验证基线同字节。

服务器已存在同 SHA canonical staging，六个关键执行文件摘要与固定候选一致；未覆盖。
首次只读取证被另一个持有原 launcher.lock 的恢复进程拒绝（观察 PID 687504，
原 lease inode 937 未变），没有进入 mutation。该进程退出后确认无活动锁、无 ba861
closure audit、安装授权仍是 ba861；再次仅发起不带 evidence 执行参数的只读取证。
向另一关联任务发送只读协调请求，尚未收到明确完成回执；不以进程退出当收尾成功。

后续只读取证成功返回 `INSPECTED_UNCHANGED_RELEASE`，证据摘要
`10ca68ab98ad6ad2f207535e8bd8a3fbb2b0d1c7cf133b003df7c80497716f0f`。
关联“更新最新代码”任务确认未启动该并发 operator，保持只读、不竞争发布。
在无活动锁且 main 仍为固定候选时，当前任务以同一证据摘要单次执行
`--retire-unchanged`；成功回执只写服务器 root-only 文件，不进入日志或命令行。
已观察 closure intent，执行尚未返回，禁止重试或按中间文件宣称成功。
此次收尾不部署、不重启服务、不改变业务数据；后续仍须独立轮换及发布门禁。

单次收尾进程 exit 0，私密成功输出按白名单回读为 `CLOSED_UNCHANGED_RELEASE`、
旧 SHA `ba861b623059661010ad38a0c4a770393075b2c6`，没有输出随机回执。
以 root-only 文件将该回执送入 canonical 新候选的 `rotate --recovery-receipt-stdin`，
绑定全新 ed25519 临时身份及六小时有效期；轮换已启动，尚未计作成功或后端发布。

轮换 exit 0 返回 `INSTALLED`，新 SHA 为固定候选、retired_sha 为旧 ba861。
经已受信管理员 SSH 读取服务器 ed25519 公钥，更新 GitHub release-production 的
专用 SSH key / known-hosts；秘密均只经内存或受保护 stdin 传递，无值进入输出。
main 仍精确为 a6b6 后，单次触发 backend-only 工作流 `35981560445`；不构建或上传
iOS，也不触及 Expo Token。当前发布进行中，未宣称线上验证或 OTA 完成。

### 本轮发布终态与新阻断

工作流 `35981560445` 的 preflight / build-permission 成功，backend 失败，服务器
固定候选终态为 `NEEDS_OPERATOR`，准备源码为 `PREPARED`。未重复 dispatch。
部署日志固定诊断 `LAYA_BLOCKED:CalledProcessError`；实际 Laya install.json 为
`PREPARING`，生成目录只包含受审资产及已创建的 venv，distribution inventory 仅 pip。
尚无生成的 service 文件或 models。因此证据把失败定位到依赖安装步骤，但原执行器
没有保留 subprocess stderr，不能将具体原因断言为网络、版本或哈希错误。

只读检查：系统 python3.12-venv 和 wheel 包已安装；PyPI、PyTorch CPU index 的 HEAD
均为 200，42 个非 torch 固定依赖版本元数据均可获取且有 wheel。这不是依赖解析或
下载完整验证，不以当前可达性证明失败时网络正常；没有重跑 pip 或改动部分安装。

失败后生产 HEAD 仍为 `05b6e4d396084103975c43e4a5fc4d044d8e66da`；backend/worker/beat
仍为 PID 261490/261492/261493，active、NRestarts=0。health 返回 healthy，数据库、
Redis、Celery connected；未认证 auth/me 返回 401。业务代码未切换，不能宣称修复上线。

新的 Laya PREPARING / generation 不符合现有“尚未安装”收尾入口；必须保留原锁、
失败审计、部分安装和短期身份，不删除、补造终态、重试原 SHA 或强行关闭该依赖。
需要独立受审的部分安装处置方案与明确授权，才可继续生产恢复。OTA 同时被 1.3.4
原生基础缺失阻断；本轮没有 OTA、原生构建、TestFlight 或商店发布。G5/G6 未完成。

### 用户授权继续至全部发布后的故障续接

用户进一步授权继续处理 Laya 半安装并构建扫码分发 1.3.4，要求持续至发布完成。
Router 选择 incident / Health Harness + safety，沿用原父 run；Codex-native adapter
负责有界协作，superpowers 全部禁用。外部调试/TDD 推荐未安装，以项目代码测试执行
同等 RED/GREEN 证据纪律。main 无分叉快进到 `e92dc30586c505e6acf82673813c0929f20441f1`，
精确 CI `35995253529` success；保留两个现有 dirty Dossier。

新只读检查发现原 a6b6 business lease 已缺失，与原失败分支应保留锁的代码不一致。
不重建锁，不把未知原因写成正常 cleanup；现有 unchanged closure 仍不适用。
计划独立审计的 partial-install/orphaned-lease 收尾，静态归档原 generation/receipt，
用完整已验证历史基线证明生产未变；独立 G4、精确 CI 和两阶段取证通过前不得执行。

原生预检确认 EAS 已有匹配本机有效证书的 AD_HOC profile，production APNs、
HealthKit=true、get-task-allow=false，有效至 2027-04-24，覆盖一个既有注册设备；
尚未证明覆盖用户当前手机。旧 1.3.4 archive 不含本次修复且为 development 签名，
不复用为本次制品。开始补扫码发布脚本的签名校验和公开文件白名单，不扩大至商店送审。

安装器原错误只有 CalledProcessError，违反可定位错误要求。新增阶段和闭集错误分类
测试先 RED：10 failed（缺少实现），后最小实现使完整 installer suite 48 passed。
第一次测试环境未配置 DATABASE_URL 导致 conftest 失败，不计 RED；随后以显式
内存 SQLite、不可达隔离 Redis 运行纯安装器单测，不涉及 DB 生产语义。
生产只做 pip --dry-run 解析诊断，不执行旧 installer、不安装包；有界短诊断超时后
继续一次完整有界诊断并保留 root-only 日志，不以超时本身断言原根因。

续接修复：新增独立 partial Laya 行政收尾，固定历史链与静态归档，不执行部分 venv、
不补造缺失 lease、不更改旧失败终态。恢复组合 264 passed；实际 Linux 两阶段取证/
执行未运行，且未知 lease 丢失仍等待用户专项风险接受。iOS QR 签名/公开文件护栏
48 passed；实际旧 archive 被 Apple codesign 校验后因 development entitlement 拒绝，
没有构建或上传新包。以上均待固定提交独立 G4。

下载诊断发现原链路吞吐瓶颈，但不能补推原丢失 stderr 的具体错误。阿里云镜像缺少
锁定 filelock 版本，已排除；清华镜像索引覆盖 42 个非 torch 固定版本。安装器改用
清华普通依赖索引和仅 torch 的官方 CPU find-links，避免 CPU extra-index 抢选普通
依赖；原 lock/hash、binary-only 与 TLS 全保留。先 RED 后完整 installer 49 passed。
完整服务器 dry-run 和 CI 原样 release-invariants 集成闸仍在运行；不把索引/吞吐或
单元测试通过当作可发布、已安装或上线证明。原生产版本保持不变。

固定 b20e8fb52 独立 G4：QR 范围 GO（独立 61 passed），依赖全新 canonical checkout、
锁定依赖、精确 CI、已验证签名和 --no-latest；不代表任意本机工作树可信或已安装。
partial Laya 范围 NO-GO：旧已认证空闲 SSH 连接不会因删除密钥自动终止。新增负例
先 2 failed，再复用现有非祖先 SSH 会话拒绝检查，在准入和撤权后 live 复证执行；
不杀无关会话。组合 321 passed、6 Linux-only skipped；Linux 闸须由精确 CI 验证。
后续固定提交复审及最终集成闸尚未完成，禁止沿用初稿为恢复 GO。
