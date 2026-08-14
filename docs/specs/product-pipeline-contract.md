# Product Pipeline Contract — 需求→上线 全生命周期流程契约(跨 agent 通用)

> **定位**:这是「一句用户需求 → 上线验证」全流程的**单一真源流程契约**,**agent 中立**(不含任何厂商专属工具名)。
> - 适用对象:Claude、Codex、Qwen、GLM、Kimi、Gemini、Grok、OpenClaw 及未来任何 coding/planning agent。
> - **每个 agent 用自己的工具去满足同一套 Gate**;具体怎么编排是各家自己的事,但**双环 + 6 道 Gate + Dossier + 失败即停**这套验收标准对所有 agent 一致。
> - Claude Code 的具体编排实现见 `.claude/skills/product-pipeline/`(它实现本契约,不另立标准)。
> - 本契约管**流程**;`AGENTS.md` 管工程硬规则;`reva-product-governance-spec.md` 管产品范围与准入。三者互不重述。
>
> **CURRENT S6–S8 OVERRIDE (2026-08-12):** 所有 repo 内自动远程/供应商 release
> entrypoint、本机 signing/install/provisioning 入口和所有 OTA/rollback channel writer
> 均冻结并须在 mutation/network 前 exit 78。EAS channel→branch 映射可能
> 漂移或共用，preview/development 也不开放。`release.py`/`release.sh`
> plan/validate/publish、`release_production_state` 联网模式与 deploy status/logs/inspect
> 也全部 earliest exit 78。当前 S6 到达 manual Gate 即 BLOCK/STOP；只允许 offline
> evidence parser、公开未认证 HTTPS、本地 Metro/iOS Simulator/test 和
> `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 的离线 IPA metadata/report（无安装
> manifest、安装二维码或可安装承诺）。`npm run ios` 固定走 Simulator
> wrapper，不得向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator
> UDID，物理 iOS repo CLI、连接/安装/验收冻结。bare `--no-upload`、
> 自动 archive/export/signing/provisioning（尤其 `-allowProvisioningUpdates`）也冻结。因此
> G5/G6/App Store submission 均 BLOCK，S8 不得标 `shipped`/`complete`。
> 解冻须另开 dossier，建立 repo-external root-owned launcher + fixed interpreter + `env -i`
> allowlist + repo-external canonical tree + source/artifact/recovery proof，并过新独立 G4。
> server-local DB migration/setup/admin utilities 属独立 manual-admin Gate，只可在生产主机
> 显式获权事件中运行，且不得由本自动 release pipeline 调用。
> Android 尚非 shipped/audited Mobile surface；`npm run android`/`expo run:android` 因
> native generation、debug signing 与 ADB install 必须 earliest exit 78，无 native CLI 例外。
> App Store `--final-submit` 会登录 production reviewer 并取得可写 bearer token，也冻结；
> 仅 non-final-submit 静态 pack 与纯静态 iOS config check 保留。所有这些允许面均不能形成
> G5/G6。
> 仓库 rc78 仅是 ordinary-invocation tombstone；Bash caller 可经 `BASH_ENV` 并覆盖
> `exit`/`builtin` function。writer legacy 必须 literal-false、语法级不可达，严禁
> source/extract/eval；`release-dmg.sh` 全入口冻结且不能兼任 checker。hostile bootstrap
> 只能由 repo-external root-owned `env -i` launcher 闭合。

## 何时适用

- **适用**:把一句用户需求走完整生命周期(需求→PRD→规划→研发→测试→部署→上线验证),或用户说「立项 / 走一遍流程 / 从需求到上线」。
- **不适用(可降级)**:单文件小修 / 纯文档 / 机械改动 → 直接做。但即便降级,**G3 测试 / G4 安全 / G5 部署健康 三道 Gate 不可跳**。

## 双环模型

```
定义环(便宜·可逆·纯文档):  需求 → S0 Intake → S1 现状勘察 →[G1 准入]→ S2 PRD → S3 规划 →[G2 可行性+安全压测]
交付环(昂贵·有闸):          → S4 需求分解 → S5 实现 →[G3 测试]→[G4 安全]→ S6 部署 →[G5 部署健康]→ S7 上线验证 →[G6 验证]→ S8 沉淀
```

**原则**:① 先把定义环吵清楚再进昂贵交付环;② 最便宜的 kill(准入、可行性、安全)前置到写代码前;③ 任何 Gate 失败 → 回指定上游,**绝不带红/带 BLOCK 往下走**。

## Dossier(脊柱 · 强制)

每个走完整流程的需求,必须有一份可追溯档案 `docs/dossiers/<YYYY-MM-DD>-<slug>.md`(模板:`.claude/skills/product-pipeline/dossier-template.md`,非 Claude agent 照其结构手建即可)。它记录:用户原话需求(逐字)/ 每阶段产出物链接 / 每道 Gate 裁决(含 REJECT/BLOCK,不藏)/ 当前阶段+状态 / 待拍板决策 / 沉淀。**任何 agent 接手先读 Dossier 当前状态,从断点续**(这是跨 session、跨 agent 可恢复的唯一办法)。

## 阶段产出物(每阶段必须留下可追溯物)

| 阶段 | 产出物 |
|---|---|
| S0 Intake | Dossier(含逐字需求 + 四问 Q1) |
| S1 现状勘察 | 现状图(已有可复用 file:line / 缺什么 / 硬约束)写进 Dossier |
| S2 PRD | `docs/prd/<date>-<slug>.md`(引用权威 PRD 的 R 号,不重 spec) |
| S3 规划 | `docs/plans/<date>-<slug>.md`(分阶段 + 数据流 + 验收 + 反馈环路由) |
| S4 需求分解 | 任务表 + 跨端 API 契约(每任务链接回规划) |
| S5 实现 | 分支(off 主干)+ commit |
| S6 部署 | 部署标识 + 回滚点 |
| S7 验证 | prod 验证记录 |
| S8 沉淀 | 经验回流 + 文档同步 + Dossier 状态=shipped |

## 6 道 Gate(验收标准 · 全 agent 一致)

### G1 · 准入 Gate(人在环)
按 `reva-product-governance-spec.md` §8 `RequirementAdmission` 逐字段过:映射 ≥1 一等对象、命中核心循环某步、安全级、自治档(新写默认 `manual_confirm`)、是否需 feature spec(§8.1)、最小端到端切片。
**裁决**:PASS / REFRAME(改写需求)/ REJECT(不做,记 Dossier)。映射不到核心循环即不做。

### G2 · 可行性 + 安全压测 Gate(人在环 · 待拍板)
进昂贵交付前,对抗式压测规划:**平台可行性**(做不到的别承诺)、**R4/R15/写自治承重墙/PIPL 合规**、范围排序。最好用**跨家族对抗**(不同模型家族评审,catch 同家族盲点)。抓到的硬阻断焊进规划;待拍板分叉 STOP 问用户。

### G3 · 测试 Gate
- 跑全部相关闸门(后端 pytest / doc-drift,mobile tsc/jest,前端 vitest+page-freeze,mac swift)。
- **部署前集成闸**:全增量测试在 CI 模式合跑(后端 `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`)。
- **绝不 `| tail`** 跑测试(`tail` 永远 exit 0,会吞掉真实退出码 → 带红上线)。直读 `passed/failed` 结果行或 `set -o pipefail`。
- 查主干 CI 真实色,别假设绿。高风险面加一次**跨家族 capstone** 评审整批 diff,专挑跨增量交互。
- **裁决**:真红 → 回 S5;假红(已知本地环境/runner 假死)→ 标注不动测试。带红绝不进 S6。

### G4 · 安全 Gate(producer-reviewer)
改动碰 用药/基因/化验/CGM/消息/Safety 规则/对外健康建议/认证/CORS/写路径 → **必经**独立安全评审。新安全行为需 feature spec + 对抗测试。**裁决**:阻断项整改 + 复审才放行;BLOCK 回 S5。安全评估每个吞异常点都是 under-alarm 漏洞 —— fail-loud,绝不静默当安全。

### G5 · 部署健康 Gate
未来解冻后，部署后跑系统健康分(本仓 `system_health_score.py`,阈值 35,低于自动回滚)+ prod 活体 smoke(服务 active + 真实路由 curl 期望 200/401 + 启动日志无 error + 新迁移表/列实查存在)。**当前裁决**:自动 release 未准入，G5=BLOCK；联网 preflight/status/smoke 也冻结，offline evidence 或公开未认证 HTTPS 不签发 mutation authority，也不等于部署健康 PASS。

### G6 · 验证 Gate(人在环)
未来解冻后，在 prod 用真实使用路径验证需求对 anchor 用户真成立(curl / 健康分 / 外部人工真机证据)。真机/发布类必经用户确认。**当前裁决**:物理 iOS 与 production mutation 均未准入，G6=BLOCK；Simulator 或只读观察不能替代。解冻后成立 → 回路闭合;不成立 → 记缺口 → 回 S5 或回滚。结果归因用「相关非因果」措辞。

## 失败即停一览

| Gate | 失败 → 动作 |
|---|---|
| G1 | REJECT/REFRAME,记 Dossier,问人 |
| G2 | 焊进规划 reframe;待拍板问人 |
| G3 | 真红回 S5;**不 `\| tail`** |
| G4 | BLOCK 回 S5 整改+复审 |
| G5 | 健康分<35 自动回滚→回 S5 |
| G6 | prod 不达成→回 S5/回滚 |

## 反馈环纪律(所有 agent 必守)

1. 长动作(deploy / 长 test；未来获准的 EAS build)**异步执行**,不串行等。
2. mobile 的 JS-vs-native 只是兼容性分类，不赋予写权限；具体路由服从项目 release
   policy。本仓所有 OTA/rollback channel、自动 production native build 与 Mac/server
   自动 production release entrypoint 均冻结并进入人工 release Gate；preview/development
   也无例外。manual-admin utility 不是此流程的兜底。
3. 部署从**干净主干 worktree**(避免把并发 WIP / 落后分支带上 prod)。
4. 并发检查:开工前查主干 + 开放 PR,不依赖别人未提交的 WIP,有状态多文件编辑用隔离 worktree,只提交自己的文件。
5. 改后端 schema → 重新生成客户端类型并同提交;加 model/规则/分区 → 同步 `docs/ARCHITECTURE.md` + `check_doc_drift.py`。

## 人在环检查点(默认)

G1 准入、G2 待拍板、G5 真机/发布、G6 上线验证 —— **显式 STOP 问用户**;其余 Gate agent 可自动过。用户可调整每道 Gate 的自治度。

## 各 agent 入口

| Agent | 经由 |
|---|---|
| Claude Code | `CLAUDE.md` → `docs/agent-skill-binding.md` → `.claude/skills/product-pipeline/`(实现本契约) |
| Codex | `AGENTS.md` §12/§13 → `docs/agent-skill-binding.md` → 本契约 |
| Cursor | `.cursor/rules/00-agents-bootstrap.mdc` → `AGENTS.md` §12/§13 → `docs/agent-skill-binding.md` → 本契约 |
| Qwen/GLM/Kimi/Gemini/Grok/其他 | `reva-product-governance-spec.md` §9.6 / §10 → `docs/agent-skill-binding.md` → 本契约 |
