# Global Agent Workflow Governance Skill 设计

**状态：** approved-for-implementation
**日期：** 2026-08-20
**范围：** 跨项目研发 Agent Skill 治理；不接管项目任务路由

## 1. 问题

Reva 已验证“唯一 Controller、Overlay 只阻断、平台薄适配器、机器 Registry”能够减少触发风暴，但其 checker、Skill ID、路由和发布目标都属于 Health 项目。直接复制成全局 Router 会产生两个问题：

- 未配置项目会被误路由到 Reva 的 Controller、Overlay 或发布流程；
- 已有项目 Router 的仓库会同时出现两个隐式 Router，再次形成控制权竞争。

## 2. 决策

首个全局产物是 `agent-workflow-governance` Plugin 中唯一的 `governing-agent-workflows` Skill。它只在创建、更新或审计“项目研发 Agent Skills 治理体系”时使用，不参与普通分析、修复、功能实现或发布。

该 Skill 只提供跨项目稳定的元合同：

1. 五种角色：`router`、`controller`、`capability`、`overlay`、`terminal`；
2. 四种生命周期：`experimental`、`recommended`、`standard`、`deprecated`；
3. 每个任务至多一个 Controller；
4. Overlay 可以返回 BLOCK，但不能拥有计划、ledger 或完成状态；
5. release 路径至多一个 Terminal；
6. 未知 role、lifecycle、source 或 schema 一律 fail closed；项目 Router 对未知 mode fail closed；
7. 研发 Agent Skill 与产品运行时 Skill 必须分开。

项目继续拥有自己的 Registry、Router、Controller、Overlay、Terminal、Gate、部署命令和领域安全规则。全局 Skill 不提供 Reva 默认值，也不在 Registry 缺失时回退到其他项目。

## 3. 边界

### 全局层可以拥有

- agent-neutral 角色与生命周期合同；
- 项目 Registry 的最小 Schema 与确定性校验器；
- 创建项目本地治理资产的操作清单；
- Plugin 内容摘要与安装完整性验证；
- 合成项目 fixture 的契约测试。

### 项目层必须拥有

- canonical modes 与自然语言到 mode 的选择政策；
- Router 和 Controller ID；
- Overlay 触发条件与 Terminal 发布目标；
- G1–G6 的项目命令、Dossier 路径、CI、部署与回滚；
- 医疗、隐私、数据库、通知或其他领域规则。

## 4. 安全与供应链合同

- v1 不含 Hook、MCP、网络访问、遥测或项目命令执行；校验器只读显式 project root 内的 Registry。
- project root 外的绝对路径、`..` 逃逸、symlink source 和未登记文件均拒绝。
- Skill 不记录 prompt、健康信息、路径、凭据或自由文本 reason。
- Plugin 使用 SemVer 和独立内容锁；更新时必须由调用者提供外部记录的上一版本与根摘要，旧 lock 缺失/篡改、同版本变更或版本倒退都必须失败。
- 安装完成必须核对 source manifest、已安装 cache、版本与 root digest，不能拿任意本地 worktree 代替发布真源。
- 本 Skill 的隐式触发边界只覆盖“治理/创建 Agent Skills 体系”，不会成为运行时 Router。

## 5. 最小项目 Registry

项目在自身仓库显式创建 `.agents/workflow-governance/registry.json`。最小合同包含：

- `schema_version`、`project_id`；
- `skills`：ID、角色、生命周期、owner、version、platforms、project-relative sources；
- `routes`：canonical mode、零或一个 controller、immediate capabilities、deferred skills；
- `overlays`：trigger 到 overlay Skill；
- `release_targets`：target 到 terminal Skill。

没有该文件时，校验器返回 `registry_missing`；它不得扫描别的仓库、用户全局 Skill 或 Reva Registry 作为默认值。

## 6. 验收

- 官方 Plugin validator 与 Skill validator 通过；
- 合成 fixture 覆盖 Registry 缺失、双 Controller、Overlay 越权、未知枚举、路径逃逸和内容漂移；
- Plugin 运行时文件不出现 Reva/Health/Claude 专属 ID 或部署规则；
- source 与安装 cache 内容摘要一致，且内容变化不升版本时拒绝重生成摘要；
- fresh Codex 任务能发现 Skill，但普通 quick-fix/feature 不由它接管；
- Reva Registry 仍由 Reva Router 裁决；一个非 Health 项目只读取自己的工程 Skill 范围；
- 原 `agent-skill-governance` Dossier 的效果 G6 继续 PENDING，不因本次提取而自动通过。
