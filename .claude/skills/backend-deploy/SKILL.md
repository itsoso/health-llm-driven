---
name: backend-deploy
description: "生产发布冻结期的后端/前端纯本地与离线证据协议。所有 repo 内自动 server release、联网计划/验证/观测入口当前 exit 78；manual admin utility 单独裁决。"
---

# Backend Deploy — Production Frozen

## 当前裁决

**所有 repo 内自动 server release entrypoint 已冻结。** 这包括 backend、frontend、all、env 同步、
health-evidence activation、App Review reset、restart、server push、release coordinator
mutation，以及以发布为目的的旧 remote-deploy、raw SSH/SCP、server-side pull/build 等
旁路。不得用 helper/环境变量绕过；入口必须在 mutation 前 `exit 78`。

manual Gate 的含义是记录 **BLOCK 并停止**，不是提供另一套人工生产命令。

server-local DB migration/setup/admin utilities 是另一类 manual admin Gate：只可在生产主机
的独立、显式、获权变更/事件流程中运行并留审计；它们不是本 skill 的自动部署步骤，任何
自动 release entrypoint 都不得调用。不能把 blocked release 临时改名为 admin event。

## 为什么 repo 内加固不足

独立评审已真实复现同 UID 可写仓库的 bootstrap 绕过：

- `refs/replace` 保持表面 HEAD SHA、改变解析出的 tree；
- shared `.git/info/attributes` + local clean/smudge filter 让执行文件被替换，同时 status
  clean、HEAD/tree 看似 canonical；
- `.git/info/exclude` 隐藏 untracked import shadow，可在 `release.py` 导入标准库前执行；
- `BASH_ENV` 与 `PYTHONPATH`/`sitecustomize` 可在 repo 内 shell/Python guard 前执行。

所以 clean worktree、canonical SHA/tree、repo 内 lock/state/receipt/proof、固定参数和
same-UID 本地验证凭证都不是 production trust root。现有协议与测试只能作为未来实现
材料，不能授权 server mutation。

`exit 78` 也只是 ordinary invocation 的 negative marker。Bash caller 可用 `BASH_ENV` 并
覆盖同名 `exit`/`builtin` function；因此 `deploy.sh`/`_run-mobile-tf.sh` 的 legacy 必须在
literal-false、语法级不可达 tombstone，runtime/operator 严禁 source/extract/eval。隔离
测试可抽取 marker fixture 做无 writer/网络的协议回归，但不构成 release proof。hostile bootstrap 只能
由 repo-external root-owned `env -i` launcher 约束。

## 当前允许的工作

`scripts/release.py` / `scripts/release.sh` 的 `plan`、`validate` 与 `publish` 都会进入 root
SSH 或带 `EXPO_TOKEN` 的 EAS channel observation，因此全部须在网络/凭证读取前 earliest
`exit 78`。`scripts/release_production_state.py` 的 `server`、`server-under-lock` 与 `mobile`
联网模式同样冻结；只保留消费调用方已有本地文件的 offline evidence parser。

`deploy.sh` 的 status/logs/inspect（含 `--inspect-release-lock`）均冻结并须在读取
lock/env 前 `exit 78`。应用层脱敏无法
抵御 `SHELLOPTS=xtrace`/`BASH_ENV` 在 repo guard 前捕获变量；锁状态只能等待
repo-external root-owned inspector，不得用 raw SSH/helper 代查。

`deploy.sh` 唯一 ordinary repo invocation 是 exact `-h`/`--help` 静态文本；它不是 hostile
caller 下的信任证明。

可以运行本地测试、静态检查、schema 校验、offline evidence parser 和公开未认证 HTTPS
观察。注意：

- 离线材料或公开 HTTPS 只描述现状，不产生发布授权，也不形成 G5/G6；
- 禁止用 repo CLI、raw SSH、provider console 或 helper 读取 production 状态；
- 禁止把已有材料中的 backend SHA、PID、health score 或 frontend BUILD_ID 写成上线成功；
- 禁止 `git push`、production publish、raw SSH/SCP/systemctl/PM2 或数据库迁移作为本
  **release skill** 的操作步骤；manual admin utility 必须另立事件流程；
- 当前 G5/G6 均为 **BLOCK**，Dossier 不得标 `shipped`/`complete`。

## 解冻设计 Gate

解冻必须新建 dossier，并由独立 G4 评审以下完整信任根：

1. repo-external、root-owned launcher，不从 same-UID 可写 checkout 启动；
2. 固定绝对路径解释器与工具链，使用 `env -i` + 最小 allowlist；
3. 从可信 remote/object identity 取得 canonical Git archive/tree，在 root-owned、repo 外
   staging materialize 实际执行字节；
4. 对 materialized source、release bundle、配置、artifact、lease/recovery 与 production
   终态做独立复证；
5. 重新跑完整 G3、独立 G4，再由人明确批准进入 S6。

任一条件缺失继续 exit 78；不能用旧协议的“full deploy fallback”替代可信 bootstrap。
