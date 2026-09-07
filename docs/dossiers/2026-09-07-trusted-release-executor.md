# Dossier: 隔离发布执行器与无手机验收

| 字段 | 值 |
|---|---|
| slug | `trusted-release-executor` |
| 创建日期 | 2026-09-07 |
| 当前阶段 | S5 实现 |
| 状态 | building |
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
- [ ] T3 固定提交安全复审、CI 与真实托管预检；发布身份缺口明确记录。
- [ ] T4 条件满足后后端部署、TestFlight 新包与终态核验。
- [ ] T5 本机模拟器导航/订单/分享回跳/审核检查；未覆盖真机项目留给次日。
- 当前 main 无分叉；已有发布 Dossier 的本地追加记录保留，不覆盖。
- 父流程 ledger：`docs/_generated/harness-runs/d46af76cd7f9.jsonl`（本地，不提交）。

## G3 / G4

尚待新鲜测试和固定提交安全复审，不把方案 GO 当实现 GO。

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
- server 安装和撤销均尚未执行；没有新增云端 secret、Expo token、构建或生产部署。

## S6 / G5 / S7 / G6

未部署、未构建；同包真机验证明日由用户完成。模拟器不替代商店 IPA 的物理设备验收或 Apple 审核结论。
