# Mobile Update Manifest

> **CURRENT SAFETY OVERRIDE (2026-08-12): 所有 OTA/rollback channel writer 冻结。**
> `production`、`preview`、`development`、Rokid、Watch 与任何 alias 都必须在 Git、状态、
> lock 和 EAS 网络访问前返回 78。本文的 manifest/transaction 内容只保留为历史协议与
> 测试设计，不授权运行 `mobile-ota.sh`、rollback、直接 EAS CLI 或控制台操作。

## 为什么非 production channel 也不能写

EAS channel→branch 映射属于仓库外可变状态，可能漂移、复用或被重新映射。channel 名称
不是 installed production cohort 的隔离证明，所以 `preview`/`development` 也不能作为
安全兜底。

此外，same-UID writable repo 已证明不能自举可信执行器：Git refs/replace、shared
`.git/info/attributes` + local clean/smudge filter、`.git/info/exclude` 隐藏的 untracked
import shadow、`BASH_ENV`、`PYTHONPATH`/`sitecustomize` 都可在 repo 内 guard 前改变执行
语义。clean tree、canonical SHA/tree、local lock/manifest/receipt 因此不能签发 mutation
authority。manual Gate 只表示 **STOP/BLOCK**。

`exit 78` 只是 ordinary-invocation tombstone。Bash caller 可通过 `BASH_ENV` 并预定义
`exit`/`builtin` function 改变顶部 guard；`_run-mobile-tf.sh` 的旧 writer 必须处于
literal-false、语法级不可达 block。runtime/operator 禁止 source/extract/eval；隔离测试
marker extraction 仅作无 writer/网络的协议 fixture，不构成 release proof。真正 bootstrap boundary
只能来自 repo-external root-owned `env -i` launcher。

## 当前允许的 Mobile 证据

- 本地 Metro、iOS Simulator、单元测试和 typecheck；`npm run ios` 固定走 Simulator
  wrapper，不得向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator
  UDID，物理 iOS repo CLI、连接/安装/验收冻结；
- `scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 读取现成 IPA 并生成离线检视
  metadata/report；不生成 install manifest、安装二维码或可安装承诺；
- offline evidence parser，以及 already-downloaded IPA/已有本地 metadata 的 identity 对账；
  release `plan`/`validate` 与 EAS/ASC remote observation 均冻结。

bare `--no-upload` 会触发 archive/export，故同样冻结；不得自动 signing/provisioning、调用
`mobile-fast-device.sh`、`mobile-local-device.sh` 或使用 `-allowProvisioningUpdates`。

Android 尚不是 shipped/audited Mobile surface。`npm run android`/`expo run:android` 会自动
native generation、debug signing 与 ADB install，故 repo entry 必须 earliest `exit 78`；
冻结期无 Android native CLI 例外。

这些证据不得写成 OTA 发布、G5/G6、App Store submission 或 `shipped`/`complete`。

## Historical schema-v2 protocol（不可执行）

若未来在新信任根下重新设计 OTA transaction，历史 schema-v2 字段可作为评审输入：

- `schema_version`、`status`、`transaction_id`；
- `platform`、`channel`、`environment`、`runtime_version`；
- `commit_sha`、`source_tree`；
- `artifact_digest`、`artifact_file_count`、`artifact_total_bytes`、`artifact_evidence`；
- `eas_cli`、`group_id`、`update_id`、`active_group_id`、`active_update_id`；
- `previous_known_good_group_id`、`previous_known_good_update_id`；
- `remote_verification`、`published_at`；
- rollback 的 source/from/active identities、verification 与 `rolled_back_at`。

历史协议要求单次 transaction 的 export 只复用同一批字节；remote outcome 模糊时只能
reconcile exact transaction，不能盲发第二次；manifest、anchor、audit 必须分离且不含
凭证、健康内容或用户标识。但这些不变量现在只可跑 mock/protocol tests，不能接 EAS。

## 解冻条件

解冻必须另开 dossier，并由 repo-external、root-owned launcher 以固定解释器和 `env -i`
allowlist 启动，从 canonical Git archive/tree 在仓库外 materialize 受信执行字节。新的
authority 必须独立证明 source/artifact/native cohort、channel→branch 与 installed cohort
隔离、exact-transaction recovery 和 terminal state，再通过新的独立 G4。当前 G5、G6、
App Store submission 均为 **BLOCK**。
