# 部署规范 🚀

> 从 `AGENTS.md §8` 拆出（2026-05-31, Agent Operating Harness Phase 2）。本文件是部署
> 硬规范的权威全文。当前裁决日期：2026-08-12。

## 8.1 当前裁决：自动 release entrypoint 冻结

当前没有获准的仓库内自动 production 发布入口。所有 repo 内自动远程/供应商 release
entrypoint 与本机签名/安装/自动 provisioning entrypoint 必须在 mutation 前 **fail
closed，exit 78**；manual release Gate 的含义是记录 BLOCK 并停止，不是改走人工命令。

冻结覆盖：

- server：backend、frontend、all、env 同步、restart、server push、health-evidence
  activation、App Review reset、release-coordinator begin/bind/mutate/finish/recover；
- Mobile：**所有 channel** 的 OTA/rollback、production native/EAS build、IPA upload、
  TestFlight selection/distribution、ASC metadata 与 App Review submission；
- Mac：Developer ID formal build/publish/recover/rollback、current/stable 切换、nginx route
  apply/rollback；
- 发布旁路：remote-deploy 脚本、用于发布的 raw SSH/SCP、direct vendor CLI、local archive
  direct upload、server-side Git pull/build、mini-program server builder 与 release helper 直调；
- Mobile install QR/public upload、bare `--no-upload` 所触发的 archive/export/signing/
  provisioning、`mobile-fast-device.sh`、`mobile-local-device.sh` 与
  `-allowProvisioningUpdates`；唯一 existing-IPA 例外是
  `--no-upload --ipa <EXISTING_IPA>` 生成离线检视 metadata/report，不生成安装材料。

禁止通过参数别名、production channel 变体、环境变量、runner override、source helper、
供应商控制台或“临时人工 SSH 发布”恢复 release 写权限。协议代码、绿测试、clean worktree、main CI、
已有 candidate 或用户口头确认都不是当前发布授权。

### 8.1.1 Manual admin Gate（不是 release 兜底）

server-local DB migration、host setup 和受控 admin utilities 不属于自动发布器，本文不将
它们声明为冻结。它们只能在生产主机上，由获权操作者针对一个独立、显式的变更/事件流程
执行，预先解析目标并保留审计/恢复证据。硬边界：

- 自动 release entrypoint 不得调用、包装或链入这些 utilities；
- release 的 manual Gate 仍是 STOP/BLOCK，不能临时创建“admin event”绕过；
- admin event 不能顺带 git pull/build、应用 release artifact、切 route、发 OTA/ASC 或
  伪造 G5/G6；超出既定 admin scope 必须停止并重新授权；
- production 凭证仍遵守最小权限、角色分离和不进 repo/log 的规则。

## 8.2 Bootstrap trust 为什么无法在仓库内闭合

独立安全评审已真实复现以下同 UID 攻击面：

1. `refs/replace` 保持表面 HEAD SHA，改变 Git 解析出的 tree；
2. shared `.git/info/attributes` + local clean/smudge filter 替换 release worktree 的执行
   文件，同时 `status` clean、HEAD/tree 看似 canonical；
3. `.git/info/exclude` 隐藏 untracked import-shadow 文件，Python release 入口可在导入
   标准库阶段执行它；
4. `BASH_ENV` 在 shell script body 前执行；`PYTHONPATH`/`sitecustomize` 在 Python
   script guard/import 前执行。

这意味着 same-UID writable repo 可以同时影响待验证对象和执行验证的程序。repo 内的
clean/source checks、Git common-dir locks、local credential/log、canonical SHA/tree、
固定 argv、remote receipt/proof 即使各自实现正确，也不能建立最初的可信执行字节。
“再加一个 repo 内 guard”不能修复 bootstrap trust。

此外，Bash caller 可通过 `BASH_ENV` 在 script body 前运行代码，并预定义名为 `exit` 或
`builtin` 的 function。于是“文件顶部打印并 exit 78”本身不能在 hostile source 下证明后续
legacy 不会执行。仓库内 78 只是一条 ordinary-invocation negative regression：

- `deploy.sh` 与 `scripts/_run-mobile-tf.sh` 如保留历史实现，必须把它放在 literal-false、
  语法级不可达 tombstone 内；runtime/operator 不得 source、抽取或 eval 该 block。隔离测试
  可抽取 marker fixture 做协议回归，但不得调用 writer/联网，也不构成 release proof；
- `apps/mac/scripts/release-dmg.sh` 整个入口冻结，原 preflight/proof 也不例外；writer-bearing
  文件不得兼任 read-only checker，checker 必须是独立且不含 writer 代码的受审文件；
- hostile bootstrap 只能由 repo-external root-owned launcher、固定解释器与 `env -i` 约束，
  不能由仓库脚本自证。

## 8.3 当前允许的 release-adjacent evidence 操作

### 8.3.1 联网 release 与 production observation 均冻结

`scripts/release.py` / `scripts/release.sh` 的 `plan`、`validate`、`publish` 实际都会进入
root SSH 或使用 `EXPO_TOKEN` 的 EAS channel observation，不能归类成无凭证只读操作；它们
必须在网络/凭证读取前 earliest `exit 78`。`scripts/release_production_state.py` 的
`server`、`server-under-lock`、`mobile` 联网模式也冻结，只保留消费调用方已有本地材料的
offline evidence parser。

`deploy.sh` 的 status/logs/inspect（含 `--inspect-release-lock`）均冻结并须在读取 lock/env
前 `exit 78`。即使其最终输出
脱敏，`SHELLOPTS=xtrace`/`BASH_ENV` 仍可能在 repo guard 前捕获 token/变量。锁状态必须由
未来 repo-external root-owned inspector 读取；不得用 raw SSH、shell trace 或 helper 代查。
其唯一 ordinary repo invocation 是 exact `-h`/`--help` 静态文本；这不是 hostile caller
下的信任证明。

允许运行本地测试、静态检查、schema 验证、offline evidence parser、公开未认证 HTTPS
观察，以及不带 `--final-submit` 的静态 App Store release-pack 与纯静态 iOS submission
config 校验。existing candidate/IPA 对账只能使用已持有的本地材料。它们只能描述观察结果：

- 不签发或恢复 production mutation authority；
- 不把本地/shared state 的 `completed_actions` 解释为线上完成；
- 不把已有材料中的 backend SHA/PID/health、frontend BUILD_ID、EAS/ASC candidate 或 Mac
  public route 状态解释为本次已发布；
- 不形成 G5/G6 PASS。

`scripts/check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得
可写 bearer token，必须在登录/凭证读取前冻结。静态校验也不能授权 ASC mutation 或
submission。同 UID 本地 credential/log 永远不能跳过 blocking suite；未来可复用证据
必须来自独立可信、精确绑定 commit/artifact 的 authority，并另过安全评审。

### 8.3.2 Mobile 本地开发与 IPA 离线检视（无 OTA 网络写入）

```bash
./scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>
```

Mobile 只可使用本地 Metro、iOS Simulator 和测试。`mobile/package.json` 的 `npm run ios`
固定走 Simulator wrapper，不得向 npm/Expo 追加 `--device`。wrapper 只从 available
Simulator inventory 解析并锁定 exact Simulator UDID；物理 iOS repo CLI、连接/安装/验收
冻结。EAS
channel→branch 映射可能漂移或共用，因此 development/preview 名称不能证明不会触达
production；所有 OTA/rollback 网络 writer 都冻结。existing-IPA 命令只生成离线检视
metadata/report，不生成 install manifest、安装二维码或上传 server，也不构成可安装证明。
bare `--no-upload` 也冻结；禁止自动 archive/export/signing/provisioning，
尤其 `-allowProvisioningUpdates`。Mac compile/test 仍属普通开发反馈；签名/公证 package
不在允许面。

Android 尚不是 shipped/audited Mobile surface。`npm run android`/`expo run:android` 会自动
native generation、debug signing 与 ADB install，且没有 exact-iOS-Simulator 目标守门，
所以 repo entry 必须 earliest `exit 78`，无 Android native CLI 例外。

Mac/nginx direct Python production CLI 与 shell wrapper 一样冻结；`release-dmg.sh` 整体不可
运行。独立 test-only harness 中的协议代码只可在 strict
non-root + explicit test mode + 固定 non-production roots（macOS `/private/tmp` 或
`/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）三个条件同时满足时运行
测试；本地 `create-candidate` 也须满足相同隔离条件，只生成候选元数据，不接触
production path/network，也不取得发布权限。

## 8.4 Gate 状态

| Gate | 当前状态 | 可记录的证据 |
|---|---|---|
| G3 | 依实际测试裁决 | 本地/CI/protocol tests（不得连接 OTA writer） |
| G4 | **BLOCK** | same-UID bootstrap trust 未闭合 |
| S6 | 未准入 | writer 的 exit-78 negative proof |
| G5 | **BLOCK** | offline evidence/公开未认证 HTTPS 不能代替部署健康 Gate |
| G6 | **BLOCK** | 未发生获准部署，不能做上线闭环 |
| App Store submission | **BLOCK** | 仅可检查材料与 existing candidate identity |

Dossier 必须保持 `blocked`，不得写 `shipped`/`complete`，也不得把协议实现、negative
tests、现成 IPA/DMG 的本地检查、已有 candidate metadata 或公开 HTTPS 观察记成上线。

## 8.5 解冻所需的新信任根

解冻必须是新的 feature/dossier，不是修改现有环境变量或删除 exit-78 guard。至少需要：

1. **Repo-external root-owned launcher**：launcher、policy 与信任配置位于 same-UID 用户
   不可写位置，owner/mode/link/type 都有外部证明；
2. **Fixed interpreter/toolchain**：绝对路径固定且自身受 root ownership/integrity 保护；
3. **Sanitized bootstrap**：从 `env -i` 启动，仅显式放行必要值，禁止 `BASH_ENV`、
   `PYTHONPATH`、Python startup hooks、Git config/attributes/filter/replace overrides；
4. **Canonical source materialization**：从固定 canonical origin/object identity 获取 Git
   archive/tree，在 root-owned、repo-external staging materialize 实际执行字节；不能从
   用户 worktree、shared `.git/info/*`、index 或未跟踪文件启动；
5. **End-to-end binding**：source tree、materialized bytes、release bundle、配置、依赖、
   artifact、签名/native fingerprint、remote lease/recovery 与 production/ASC terminal
   state 必须独立绑定；
6. **Recovery**：在每个 mutation/crash boundary 完成 exact-transaction 恢复演练；未知
   结果保留现场且 BLOCK，不能盲重跑或用新 checkout 重建恢复语义；
7. **重新过闸**：新的 G3、独立 G4、人批准 rollout，以及按 surface 单独设计的 G5/G6。

这些条件必须先落地和受审，本文才可新增 production runbook。旧 repo-contained
server/Mobile/Mac 协议可作为设计输入，但不得直接“解开开关”。

## 8.6 冻结期仍需保持的未来协议不变量

这些不变量用于测试和未来设计评审，不授权执行：

- server：数据库 backup/restore rehearsal、managed migrations、schema probe、runtime
  authorization、writer quiescence、revision/PID/health、rollback/finalize 永不因 cache 跳过；
- proof reuse：same-UID local evidence 只可 shadow/diagnostic；missing/corrupt/drift 不得变成功；
- Mobile：未来任何 OTA channel 都必须证明 channel→branch 与 installed native cohort 的
  隔离和绑定；build creation、TestFlight
  selection、same-build physical acceptance、App Review submission 是独立 Gate；
- Mac：Developer ID signing/notarization、immutable bytes、current/stable、root-owned receipt、
  high-water、route/public HTTPS proof 与 recovery 必须绑定同一 exact transaction；
- release state：本地 state 只作审计；生产完成只由新鲜、无歧义的外部事实证明；
- logs/manifest：不得含密钥、审核密码、健康数据或用户标识；测试禁止用 `| tail` 吞退出码。

## 8.7 生产配置与基础设施边界

- `.env`、ASC key、migration credential 和 signing material 不进 Git、Dossier、日志、
  local release state 或聊天内容；
- runtime DB role 与 migration role 分离；migration role 不得是 superuser/BYPASSRLS；
- 生产服务、PostgreSQL、Redis、internal metrics 不直接暴露公网；
- root-owned receipts/journals、runtime data、uploads 与 caches 位于 Git checkout 外；
- 自动 release 冻结期间不得由 release entrypoint 同步生产 env、重启服务、修改
  nginx/systemd、重置审核数据或手改远端 lease/current/receipt。独立 manual admin event
  只可执行其获批 scope，绝不能接续发布或形成 G5/G6；只读检查发现异常时保留证据并升级。

长期密钥管理见 `docs/ops/secrets-management.md`；安全事件处理见
`docs/governance/security.md`。
