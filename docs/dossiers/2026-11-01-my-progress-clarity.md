# 我的进度页面优化

| 字段 | 值 |
| --- | --- |
| 状态 | released_acceptance_partial |
| 当前阶段 | G5 delivered：后端与 OTA 已发布；G6 自动线上证据 PASS，交互与设备接收未验证 |
| Controller | health-harness-orchestrator; safety-gate overlay |

## G1 准入

裁决: PASS

用户截图要求优化现有进度页，范围是执行回顾、指标观察和建议详情的信息层级、
空状态及错误比例。规格：docs/specs/2026-11-01-my-progress-clarity.md。
不新增健康写入或自主建议，不将指标相关变化宣称为 AI 导致的改善。

## 范围与基线

已授权的隔离 worktree 续用，基线 bd4a4f4f795f6ae25e6825a7adf35bcff0efd738。
共享 main 的其他未提交改动保持原样。源码确认 graded 与 completed 并非子集，
原页面有 0/0、2/0、零行动 0% 和不恰当因果文案；当前任务仅调整展示与读取边界。

## 验证及首次发布（9a 历史阶段）

- UI RED: 原页面 8 个行为用例失败；随后补前后记录完整性及专业复核提示 RED。
- Session RED: 原服务 10 个隔离用例失败，另补两个旧 refresh 回调失败用例。
- 新鲜定向 GREEN: 页面、结果颜色、session hook/service、既有 review 共 5 suites / 45 tests。
- TypeScript、设计 token、System Map / 导航与文档漂移检查通过；新增页面测试引起地图路由计数由生成器同步。
- CI=true 全量移动端：主套件 382 suites / 3905 passed / 1 existing skip；隔离输入框 84、聊天 88、认证 34、GPS 7，合计 4118 passed。最终 useMemo 引用整理追加 hook 10 tests 通过。
- 本地 Simulator Release 构建成功；打包发生于最终 useMemo 整理前，不作为最终候选点击验收。Mac 锁屏阻挡实际点击，设备接收 OTA 也未验证。
- 独立 G4 GO 绑定累计候选 `9a530fd2778ad8b8134a16db2941a4365d9d9836`，独立回归 4 suites / 41 tests；最终 tsc、定向 ESLint、秘密扫描、diff check 通过。
- [精确主干 CI 41277052617](https://github.com/itsoso/health-llm-driven/actions/runs/41277052617) 全部 32 jobs 成功。
- [发布 validate 41277698865](https://github.com/itsoso/health-llm-driven/actions/runs/41277698865) 成功。
- [后端发布 41278851235](https://github.com/itsoso/health-llm-driven/actions/runs/41278851235) 成功；服务器 `/var/lib/reva-release/9a530fd2778ad8b8134a16db2941a4365d9d9836/completed.json` 为 SUCCEEDED，生产 SHA 匹配，health-backend / celery-worker / celery-beat 均 active。
- 部署健康评分 60/60；公开 `/api/v1/health` 返回 200，匿名进度与 review 读取均返回 401。
- [OTA validate 41279223434](https://github.com/itsoso/health-llm-driven/actions/runs/41279223434) 成功。
- [OTA publish 41279412983](https://github.com/itsoso/health-llm-driven/actions/runs/41279412983) 失败，官方诊断为 `claim-ota` / `command_failed`。失败时原操作保留 `intent.json` 与 `lease.json`，没有 `claimed.json`、vendor receipt 或完成回执；当时业务 lease 尚未收口；现已按下文关闭。后端成功不代表 OTA 已发布或设备已接收。

## 首次发布准备异常及收口（9a 历史阶段）

首次 canonical staging fetch 在 180 秒超时；原失败回执保留。只读发现对象已完整落盘，六文件库存、FETCH_HEAD 和 fsck 均验证通过。首个受限 checkout 续接因旧版本仅发布后端、没有 build.lock 而在任何远端 intent / checkout 前失败，记录继续保留。

独立审查后的精确无 build.lock 续接只持既有 launcher 锁，反复验证锁持续不存在、原对象及两组失败证据不变；未重新 fetch、清理、备份或重发部署。原 source 完成 checkout，独立本地/远端完成回执及干净 HEAD 验证通过。服务器审计路径为候选 bootstrap 下 `stage-continuation/`，completed SHA256 `00f30aac25de2f8b1251791f1c7859045ba96a5303a3617d8716b962254b75bc`。

同权限只读 App credential 首次刷新 `progress-read-credential-9a530fd2-v1` 成功，本地与远端回执相同；canonical 授权从 `bd4a4f4f795f6ae25e6825a7adf35bcff0efd738` 成功轮换到候选，随后只执行一次 backend 发布。所有原失败、审查及成功回执保留，未备份或恢复旧配置。


## OTA 领取前失败与恢复准备（历史阶段）

固定 profile 绑定原候选 `9a530fd2778ad8b8134a16db2941a4365d9d9836`、run
`41279412983`、attempt `1`、job `124768075123`、artifact `13072503978`
（2565 bytes）。官方 ZIP、三份规范 JSON 及原候选四项控制流源码摘要均已核对；
`SOURCE_HASHES` 来自固定 `git show 9a530fd…:<file>`，不取当前工作区字节。
profile 只允许关闭此未发布失败，不生成 OTA 成功回执、不重发原 operation。
全部四个 lease 文件强制绑定 device、inode、内容摘要与 `ctime_ns`，历史 profile 边界保持。

- 本地 profile 提交：`44b1a3fb1406ad35b78360366c27fb4e2ea80a44`，此处记录当时尚未 push 的状态；后续已纳入下文 fad 候选。
- RED：未支持新 profile 时 25 failed、35 setup errors，均因未知固定 profile；8 passed。
  GREEN：完整关闭器回归 396 passed、3 expected legacy-schema skips，diff check 通过。
- 独立 G4：reviewer `diet_detail_safety_review` 明确 GO，绑定上述 44b 提交；独立重复
  396 passed / 3 expected skips，并核对官方 metadata、ZIP 与控制流摘要。证据为评审消息，
  尚无单独持久报告文件。
- 该阶段原失败及 intent/lease 保持原状，尚未执行关闭；后续关闭结果见下文。
  必须由后续精确绿色 reviewed SHA，重新核验原租约、双锁、后端终态及健康后才可执行。
- 无 profiling 的 canonical 只读诊断成功：prepare 2.93 秒、本地完整校验 221.28 秒，
  `COMPATIBLE`、exit 0；保护文件与原 lease 身份摘要的两项 unchanged 均为 true。
  带 profiling 的校验耗时 550.64 秒，仅最后有效期检查失败；该插桩时间不能作正常基线。
  两次诊断都未复现原 publish run 的失败，直连 GitHub 元数据 TLS 超时也不作根因证据。
- 正常本地校验距旧 240 秒有效期仅余约 19 秒，原代码的 120 秒基线注释已过时。
  以此预算风险为依据，将固定 TTL 最小调整至 480 秒（约新正常基线两倍，低于
  server 600 秒 / publisher 900 秒），不改 CI 后起算、消费前后过期检查、单次消费及
  生产 revision/历史/租约/健康校验。这是余量修正，不是已确诊的原失败根因修复。
- TTL RED：313 秒及 480 秒的完整本地校验模拟在旧预算下失败（2 failed / 4 passed）；
  313 秒是测试压力场景，不是线上实测。GREEN：`scripts/test_testflight_only.py`
  全部 48 passed，包括 481 秒前后过期拒绝、失败后不可复用及既有生产漂移检查。
  追加 CI=true 发布关联八套件回归 1092 passed / 4 skipped / 7 duplicate-ZIP 负向测试 warnings。
  该阶段要求重新 G4 与精确主干 CI；44b 的 GO 不覆盖新增 TTL 修改。
  原失败 operation 不得重发、清锁或伪造终态；后续按固定 profile 关闭。


## 展示及数据边界

本期行动、身体变化与建议进展分区；不把零分母变成零分，不使用 graded/completed
漏斗。前后记录必须完整、有限且至少两次；涨跌中性显示并保留观察性边界。
评估说明默认折叠，专业复核提示保持可见。保留周期切换、建议详情及周导航。
双区块刷新，失败按区块展示安全重试，不暴露原始错误。按 owner/consent revision/
auth generation/window 隔离读取，旧响应及旧 refresh 回调不可进入新会话。


## 新候选发布结果（本地收尾草稿）

当前候选 `fad537e2cb4e6d81a219d4ab5791d3896a5bd1d2` 已获独立 G4 GO，
覆盖固定 9a 未发布 claim 关闭 profile 与 TTL 480 秒修正；依据父流程评审消息，
不虚构单独 G4 报告路径。[精确主干 CI 41282280573](https://github.com/itsoso/health-llm-driven/actions/runs/41282280573)
全部 32 jobs 成功；[发布 validate 41282914986](https://github.com/itsoso/health-llm-driven/actions/runs/41282914986)
成功，7-job roster 为 preflight 成功、其余六项预期 skipped。
本地官方 JSON 分别为 `/private/tmp/reva-progress-fad537e2-ci-verified.json` 与
`/private/tmp/reva-progress-fad537e2-validate-verified.json`。

- 诊断结论保持：无 profiling 完整本地校验 221.28 秒且 COMPATIBLE；带 profiling
  550.64 秒仅最后 TTL 检查失败。两次均未复现原 publish 失败，480 秒是预算余量修正，
  不把 profiling 耗时或 TLS 超时写成原失败根因。测试证据见前述历史阶段。
- 新候选 staging 的完整 fsck 在 180 秒超时，原失败证据保留；首次续接误拒标准
  lease-parent lock alias，在任何远端写入前失败，证据同样保留。最小修正续接脚本
  SHA256 `5c7309c5e75ca79f3747207fc6159bbdf95776646f310e875aa163238a129f21`
  经独立 G4 后执行，完整 fsck 287.36 秒成功，未跳过 fsck 或重新 fetch。
  父流程独立 canonical 读回确认干净 HEAD 为 fad；续接本地完成回执 SHA256
  `7e97211b994860697401522b53076d239cb01e959511c364a74853b7fd0808ea`，
  远端审计目录 `/var/lib/reva-release/bootstrap/fad537e2cb4e6d81a219d4ab5791d3896a5bd1d2/stage-continuation-fsck900-lease-parent/`。
- 固定 9a 原操作 inspect / apply 成功，canonical 终态为 `CLOSED_UNPUBLISHED_CLAIM`，
  closure 摘要 `c249bdd37b41cbe26e18c05ba4cfcd7034c9fd3eb3fd2bb42311940d49fe39d7`。
  父流程独立 `validate_closed_history` 读回通过，business lease absent；原操作与失败
  证据保留，无 vendor receipt，未伪造 OTA 成功。关闭 intent / completed 原始字节摘要
  分别为 `d5af3b726b0882126edb2ee415757a69609b28eb991c0c4bad013a03b260a7b4` /
  `4cb3d6d85726e483938de56a7bb4dec97d9abc7dae29e3ae9c404c30e86b69a6`。
  独立读回绑定：`/private/tmp/reva-progress-fad-postclosure-bindings.json`。
- 同一 App、同一仓库、相同只读权限的刷新 `progress-read-credential-fad537e2-v1`
  成功，状态 `READ_CREDENTIAL_REFRESHED`。安装凭据摘要
  `cb8de684280037f36fbcd2515937b8b7b9092df1dfa3a1171394c3d38e9007a1`，
  expiry `1793522014`；本地与远端完成回执及独立读回匹配，仍确认 business lease absent。
  本地回执 `/private/tmp/reva-release-ops/progress-read-credential-fad537e2-v1/completed.json`，
  SHA256 `0f840ffc8bd485963dc182cf7ee29ac655473067af34f731721d69b96dd1cf8e`；
  独立证据 `/private/tmp/reva-progress-fad-refresh-independent-readback.json`。

- 9a → fad 授权轮换脚本 SHA256
  `4525a367ddf85b72577344301a1d5802c91701e77a882f0f8e959040983e2ab3`
  仅执行一次，结果 `INSTALLED`。父流程独立读回确认 policy / executor 匹配，
  business lease absent；授权轮换成功与制品发布分开记录。
- [后端发布 41285765970](https://github.com/itsoso/health-llm-driven/actions/runs/41285765970)
  成功，精确绑定 fad。父流程独立验证 production HEAD 为
  `fad537e2cb4e6d81a219d4ab5791d3896a5bd1d2`，该 SHA 的 completed 回执为
  `SUCCEEDED`；health-backend、celery-worker、celery-beat、reva-laya 四服务 active。
  公开 health 返回 200 / healthy，匿名 progress 与 review 读取均返回 401。

- [OTA validate 41286197908](https://github.com/itsoso/health-llm-driven/actions/runs/41286197908)
  成功，`native_source` 为 `PREFLIGHT_PASSED`；随后
  [OTA publish 41286450435](https://github.com/itsoso/health-llm-driven/actions/runs/41286450435)
  成功，精确绑定 fad。父流程独立服务器读回确认 completed 为 `SUCCEEDED`、
  business lease absent；vendor group `ab1103f9-ce78-4298-a579-edef09ccc132`，
  update `01a1961e-4d8e-7939-a8a4-8145cda6263a`，runtime `1.3.6`。
- 公开官方 endpoint 经 strict multipart 解析及 `contract.validate_manifest` 校验，
  manifest 中 launch 与全部 47 个 asset 的 hash 均与本次 claimed artifact 一致；launch hash
  `grf1Pa1sLKDio9RcSh0hOZLVP4YuPtdAfAtzos54-Iw`。本地默认 urllib 请求首次返回
  403，改用发布器相同请求头与既有本机代理读取同一官方 endpoint 后成功；该过程仅为
  只读验证，没有重发 OTA。独立证据：
  `/private/tmp/reva-progress-fad-ota-independent-server.json` 与
  `/private/tmp/reva-progress-fad-ota-public-manifest-proof.json`。
- 本次 claim 实际耗时 291.45 秒，高于旧 240 秒、低于新 480 秒预算；这支持增加余量，
  但不构成原 9a 失败根因的直接复现，原失败记录与 `CLOSED_UNPUBLISHED_CLAIM` 终态保留。

G5 delivered：精确 fad 后端与 OTA 均已发布，G6 自动线上证据 PASS。模拟器实际点击仍因
Mac 锁屏未验证，设备接收本次 OTA 也未验证；不能宣称全部验收完成，不能以公开 manifest
校验替代设备接收或用户交互。状态为 `released_acceptance_partial`，后续只补充缺失验收证据。

本次后续 Dossier 更新仅记录发布证据，使用纯文档轻量 CI；依据
`docs/governance/deploy.md` 持续授权规则，不触发无关制品发布。
