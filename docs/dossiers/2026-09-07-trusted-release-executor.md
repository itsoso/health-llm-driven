# Dossier: 隔离发布执行器与无手机验收

| 字段 | 值 |
|---|---|
| slug | `trusted-release-executor` |
| 创建日期 | 2026-09-07 |
| 当前阶段 | S8 发布后本机验证完成（正式 App Review 不在本轮范围） |
| 状态 | complete |
| 负责 | Codex |
| 反馈环 | 本地负例测试 / GitHub 无凭据预检 / 独立安全复审 / 后端部署 / TestFlight / iOS Simulator |

## S0 · 用户需求（逐字）

> 修复掉，另外发布之后，本机先执行模拟测试和审核验证，通过之后明天我再用手机进行测试。不用等我，我拔掉手机

修复已推 main 的饮食产品提交 `6da24bbaf`，但现有工作区启动的发布链被独立安全复核 NO-GO。本轮允许修复该基础设施和发布，不依赖物理手机，不包含正式 App Review 或公开上架。

## S1 · Discovery

- `deploy.sh::push_code` 复用生产备份/恢复/回滚，当前强制 push；脚本在验证源前申请远端 lease。
- `scripts/_run-mobile-tf.sh` 从本机工作区动态运行 CLI，还会容忍脏树；不能用于新的受信路径。
- 当前 GitHub 只有 CI workflow，没有发布 secrets。本机 sudo 需要交互，不能把本机目录 chmod 当作独立信任根。
- PR #252 提供威胁证据，未合并的规范不自动适用；不合并其大范围冻结及产品修改。
- 模拟器 iPhone 17 Pro / iOS 26.5 已启动；通过显式 DEVELOPER_DIR 可用，默认 xcrun 找不到 simctl 是工具选择问题。

## G1 · 准入裁决

- first_class_objects：发布制品、验证证据；支撑健康记录的可靠交付，不新增健康业务对象。
- core_loop_step：实现 → 验证 → 部署 → 使用验证。
- target_surface：发布基础设施；safety_level：privacy_sensitive；autonomy_tier：manual_confirm（本轮用户已授权）。
- spec_required：yes；最小切片是 GitHub 托管新 VM 的精确 main 发布，保留已有事务安全闸。
- **裁决：PASS**。用户明确要求修复和继续发布，调整 G1/G2 自治度为无分叉时继续，无需重复询问。

## S2 · PRD

- `docs/prd/2026-09-07-trusted-release-executor.md`
- 不提升健康写自治、不迁移数据库、不合并其他 PR、不提交 App Review、不使用手机。

## S3 · 规划

- `docs/plans/2026-09-07-trusted-release-executor.md`
- GitHub 控制面和审核过的 exact SHA 是信任前提；不宣称能抵御已取得 runner root 的攻击者。

## G2 · 可行性与安全压测

- 独立 reviewer 判 GitHub 托管新 VM 方案有条件 GO：必须先进行无生产凭据的 exact SHA/main/CI 检查，再进入受保护的凭据阶段；锁、备份、恢复和回滚不跳过。
- root-owned 源不等于能防 runner 内任意代码；不运行 PR 脚本，不复用测试机或可污染缓存，固定工具和安装清单。
- **裁决：PASS（实现与无凭据验证）**。实际生产执行仍必须有配置好的最小权限凭据及 G4 GO；无凭据时可靠阻断，不用本机个人私钥填充新云端权限。

## S4 · 任务

- [x] T1 精确 revision/CI 只读守门与负例测试。
- [x] T2 独立托管 workflow，默认无凭据预检；后端只验证不 push 的兼容模式。
- [x] T3 固定提交安全复审、CI 与真实托管预检；使用可撤销的短期发布身份。
- [x] T4 后端部署、TestFlight 新包与终态核验。
- [x] T5 本机模拟器登录/隐私/取消注销/分享回跳及线上合成订单检查；明确真机与弱网边界。
- 当前 main 无分叉；已有发布 Dossier 的本地追加记录保留，不覆盖。
- 父流程 ledger：`docs/_generated/harness-runs/d46af76cd7f9.jsonl`（本地，不提交）。

## G3 / G4

以下保留逐轮裁决；最终 G4 GO 见发布后记录，不把方案 GO 当实现 GO。

- 首轮固定提交 `9ff10f95342cfaef96011061ff268a108746ed58` 的 G4：**NO-GO**。
  两项阻断：授权剩余窗口不足仍能启动，以及 workspace 新目录项未 fsync 父目录。
  已补部署上限 3600 秒＋恢复余量 3600 秒，在启动、准备后及最终 CI 后重新检查；
  已消费标记后、任何 prepare/deploy 前 fsync STATE，失败保留 STARTED 并阻断。
  新增边界和故障注入回归通过；修复提交仍须独立重审，不凭 producer 自评放行。

- `238b30107463dd5a5ceb20149f7ed4fcfe1da23b` 独立 G4 **GO**（server 64 passed），
  本地最终集成 365 passed / 192.36 秒；main CI `34137743030` SUCCESS，
  云端无生产凭据 validate `34138358246` SUCCESS。
- 真实 bootstrap 的只读 Git clone 暴露网络兼容性：隔离环境去掉 root global 的
  HTTP/1.1 后，默认 HTTP/2 连接约五分钟未收到新数据，pack 仅 16 KB。
  终止该只读下载后，显式 HTTP/1.1＋低速边界的同一 canonical clone 成功，objects 22 MB。
  不恢复 global config；将固定 transport 设置覆盖 source 准备和 deploy.sh 的所有 Git 子进程。
  新提交需重新 G4/CI/validate；此时仍未安装服务器授权或启动后端发布。

### 实现与验证证据（发布前）

- 原产品提交 `6da24bbaf786f55c819563d42f847a04833af02d` 的真实 CI
  `34133080315` 已 SUCCESS；临时 live-eval 确认变量已删除。本次基础设施提交仍须自己的 CI。
- source verify-only 用真实 Git fixture 做 RED/GREEN：10 项通过；原 release/rollback
  集成初次 326 项通过。bootstrap、一次性 RPC 与撤销恢复身份的最新负例共 125 项通过。
  最终 CI-mode release/rollback/bootstrap/receipt/archive 组合闸 **358 passed，180.35 秒**，
  `/tmp/xiaoba-release-integration-final.log`；System Map、Dossier 和包含新增文件的秘密扫描通过。
- 独立模拟器 bundle `life.executor.health.dietaudit`，同源真实分享组件的 XCTest
  2/2 PASS、0 failure、19.402 秒；验证编辑→预览→复盘关闭 Modal 回 root Agent、
  取消不发起复盘。未改动主 App 草稿，未连接物理手机。
  证据 `/tmp/xiaoba-diet-native-qa.bifyx4/baseline-native.xcresult`。
- EAS CLI 固定 `23.2.0`，同 major 依赖覆盖 minimatch/nanoid/tar/ajv/joi/yaml；
  npm audit 从 4 high/12 moderate/1 low 降为 **0 high/0 critical/9 moderate/1 low**。
  `--version` 与真实 `build:inspect -p ios -s archive` 成功（约 20 MB）；该命令没有发起构建。
  剩余 advisory 必须提交 G4 评估：uuid 的 v3/v5/v6 buffer 路径（已检索调用为 v1/v4），
  ts-deepmerge 位于新项目初始化而非 build，diff 使用 diffLines 而非受影响的 patch API。
  不声称零漏洞，也不为消除报告盲目跨 major 替换厂商 API。
  证据 `/tmp/xiaoba-release-tools-audit-final.json`、`/tmp/xiaoba-eas-toolcheck.QlUtq0/inspect.log`。
- 上述初次证据采集时 server 安装和撤销均尚未执行；实际安装、发布及撤销结果见下节。

## S6 / G5 / S7 / G6

### 2026-09-08 · 最终固定提交与真实发布

- HTTP transport 修复 `fcbf01329dfeabbd22ef83aea56394e93abb9b00`：独立 G4 GO、
  CI `34139659079` 和 hosted validate `34140373606` SUCCESS。真实安装后的认证负例发现
  OpenSSH 8.9 不接受 `expiry-time` 的 Z 后缀；此时没有启动 backend，也没有消费记录或业务 lease。
- TDD 修复为服务器系统时区无 Z 的时间，清除 caller TZ，并 roundtrip 核对绝对截止时间；
  保留八小时授权上限和 7200 秒启动窗口。固定提交
  `34e32edc463d87a3331d38d552599d3c164c3db3` 独立 G4 **GO**（98 项独立回归）；
  parent targeted 139 PASS，全 CI-mode 发布合同 **577 PASS / 281.93 秒**。
  CI `34141329002`、hosted validate `34142232595` 均 SUCCESS。
- 经独立 reviewer 允许，用旧 fcb canonical bootstrap 撤销精确旧授权；持全局锁重新证明
  NEVER_STARTED / 无业务 lease / 无发布进程，再将两个旧安装目录原子移入 root-only retired 审计目录。
  未删除或重建 launcher.lock、消费标记、业务状态或其他授权。
- 新安装的真实正负检查通过：status READY、loopback 认证成功；任意命令、错误 SHA、参数注入、
  SFTP 和错误主机 pin 均拒绝。只触发一次 `target=release`，run **34142442888 SUCCESS**。
- Backend `deploy.sh -b` 完整通过：dump 23 秒、恢复演练 20 秒、站外加密/上传/远端哈希与 HMAC
  验证 364 秒；精确 live SHA 为 `34e32edc4…`，服务 active，健康度 **58/60 PASS**，终态 SUCCEEDED。
- EAS production **1.3.3 (265)**：build `71b2da1d-b4ea-4f9d-82b2-43eb2dd54849` FINISHED，
  source SHA 与上述发布一致；submission `9e83f974-1ea7-43b4-9f22-709e2b32ebae` 于
  00:37 CST 上传成功。ASC build `a05ef842-3268-4f9c-bad6-093d37b3c951` 上传 Complete，
  已分发至 Team (Expo) 与内部测试；What to Test 已保存。没有提交正式 App Review。
- 下载的实际 IPA 配置校验 PASS：小巴健康、1.3.3/265、iPhone portrait、无 Watch/extension、
  权限文案与隐私清单匹配，DTXcode=2620、iOS SDK=26.2；新饮食复盘文案及组件标识在 bundle 内。

### 发布后验证与边界

- 饮食 API 真实模型合成订单：四项食品/数量、广告排除、确认写入、数据库回查、重复确认幂等，全部 PASS。
- 主 Agent `记录晚餐`＋合成订单图：识别为 order_estimate/order_quantity。实际置信度较低，
  正确保留 diet_draft 确认卡，而非误称营养标签缺克数；确认后写入/回查/幂等均 PASS。
  初次 QA SSE 解析器错误地把 JSON 内 event 当作独立 SSE event，并过严要求自动保存，因此失败；
  按原 client_turn_id 只读恢复同一回合，验证后确认同一草稿，没有重发请求或降低生产置信阈值。
  本次新建的合成记录与合成对话均已精确清理，既有记录没有被删除。
- 新建空白 iPhone 17 Pro / iOS 26.5 Simulator，不克隆或重置原设备：审核账号安全登录 1/1、
  完整 App 两次冷启动持久化/隐私页返回/取消注销 3/3、真实原生饮食组件取消/分享回跳 2/2，
  最终 **6 项全部 PASS，退出码均 0**。主 App 的既有登录与未发送草稿未触碰，未使用手机。
- 保留两次 QA 初始失败：旧模拟器记住的凭据导致 Paste 追加，改用全新空白设备解决；
  XCTest 首次 tap 仅自动滚动，改为先显式滚动到可见/可点击再 tap，产品代码未改。
- 本机汇总 `/tmp/xiaoba-full-release-qa.6R1NXb/POST_RELEASE_RESULT.json`；
  API `/tmp/xiaoba-release-order-api-result.json`；Agent确认 `/tmp/xiaoba-agent-order-confirm-result.json`。
  临时原始失败证据保留，不以重跑通过隐去原因。
- 审核资料/config 自动 gate PASS，线上隐私页 HTTP 200；本轮 G5/G6 仅裁决部署、内部 TestFlight
  分发和上述本机验证 **PASS**。同源 Simulator 不是商店 IPA 真机运行；完整 App 饮食页面→真实 Agent
  的整条 UI、隔离弱网恢复、相机/语音/生物识别/外部分享与同包真机验收仍由用户白天复测。
  正式上架 final-submit gate、同包截图人工审核与 Apple 结论均未宣称完成。

### 凭据与现场收尾

- Backend SUCCEEDED 且全部发布 job SUCCESS 后，精确撤销两条 task SSH 授权；实测专用 key 已被拒绝。
  原有密钥保持不变。删除本次本机私钥、服务器新旧两份已撤销 loopback 私钥及临时 deployment.env，
  不影响 live backend/.env；其余 root-only 安装、日志及一次性状态保留审计，不重置用于重跑。
- 删除本轮创建的三个 GitHub release-production secrets，查询列表为空；撤销并删除本轮新建的
  Expo robot token，既有 robot 与个人认证不变。新旧模拟器剪贴板均清空、临时凭据 broker 已停止。
- 下一次发布需要新的受审授权生命周期；不能复用已撤销身份或清除本次消费记录。
