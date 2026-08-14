---
name: health-harness-orchestrator
description: "复元健康平台的代理团队编排器。当用户要在本仓库做跨端功能/修复/上线 —— '加一个功能'、'实现 X'、'修这个 bug'、'合并部署'、'发 OTA / TestFlight' —— 用本 skill 组队协作。后续:部分重跑、补充改动、再次上线时也用本 skill。"
---

# 复元 Health Harness — Orchestrator

把本仓库的专职代理(`backend-engineer` / `mobile-engineer` / `qa-verifier` / `safety-privacy-reviewer` / `release-engineer`)编排成一个团队,完成"计划 → 实现 → 验证 → 安全评审 → 上线"闭环。

## 执行模式:代理团队(默认)
2 个以上代理协作时优先组队(`TeamCreate` + `SendMessage` + `TaskCreate`),团员自调度、互相质疑、共享发现。所有代理 `model: "opus"`。

## Run Ledger(checkpoint / budget / trace)

凡是跨 2 个以上代理、可能被中断、或需要对抗评审的工作,先建本地 JSONL ledger:

```bash
python3 scripts/harness_workflow_trace.py init \
  --kind health-harness \
  --dossier docs/dossiers/<date>-<slug>.md \
  --budget-tokens <hard-limit> \
  --label "<short label>"
```

- 把输出的 `run_path` 记录到 Dossier「研发任务/验证记录」里;原始 JSONL 在 `docs/_generated/harness-runs/` 本地保存,不提交。
- 每次派生/裁决用一等命令追加:`spawn --run <run_path> --phase "Phase 2" --agent backend-engineer --task-id <task-id> --tokens <n>`;`verdict --run <run_path> --phase "Phase 3" --agent qa-verifier --task-id <task-id> --status passed|failed|blocked`。阶段检查点仍用 `event --event checkpoint --phase "Phase 2"`。
- `event` 返回码 `2` = 预算将超限,必须 STOP、缩小范围或重新拍板,不能继续 fan-out。
- 中断恢复时先跑 `summary --run <run_path>`,从 `latest_checkpoint`、`open_agents` 和 `open_tasks` 继续。

## 团队构成

| 团员 | 类型 | 职责 |
|---|---|---|
| backend-engineer | 自定义 | `backend/` 实现(API/service/model/agents/twin/safety/迁移) |
| mobile-engineer | 自定义 | `mobile/` 实现(屏/组件/hooks/services/主题) |
| mac-engineer | 自定义 | `apps/mac/` 实现(Swift/SwiftUI;`mac-build-deploy` skill) |
| frontend-engineer | 自定义 | `frontend/` 实现(Next.js 14 Web;注意页面冻结) |
| qa-verifier | general-purpose | 跑闸门(pytest/doc-drift/tsc/jest/swift/前端 vitest+page-freeze)+ 跨界 shape 比对 + 真红/假红判别 |
| safety-privacy-reviewer | 自定义 | AGENTS.md 硬规范 + 医疗安全/隐私评审(高风险改动必经) |
| release-engineer | 自定义 | production freeze 审计；offline evidence/public unauthenticated HTTPS + Simulator/existing-IPA offline inspection |

## 工作流(混合:计划→实现 fan-out→增量 QA→评审→上线)

### Phase 0:上下文 + 范围
- 读 `CLAUDE.md` / `AGENTS.md` 相关章节;判断改动触及哪些层(frozen core / agent fleet / mutable business)。
- 新功能先跑 feature-plan 四问(`~/work/personal/PRACTICES/feature-plan.md`):谁用 / 解决什么 / 数据流 / 边界。
- **并发检查**:`git fetch` + `gh pr list`,确认没被其它分支/agent 抢先(本仓库并发多,工作易被取代)。

### Phase 1:计划
leader 拆任务 → `TaskCreate`。跨端任务先定 **API 契约**(请求/响应 shape),写进 `_workspace/`,让前后端对齐。

### Phase 2:实现(fan-out,团队)
- 按任务触及的端并行:`backend-engineer` ‖ `mobile-engineer` ‖ `mac-engineer` ‖ `frontend-engineer`;后端定下 shape 后 `SendMessage` 给各端对齐类型/hook(Web 注意页面冻结,默认不开新页)。
- 隔离原则:并发 agent 会切分支 → 有状态编辑用 `git worktree`(显式 commit hash 建,见 `using-git-worktrees`),edit→build→commit 在隔离工作树里;别把 build+push 放进同一并行批次。
- 每个 fan-out 分支创建/完成/阻断都写入 Run Ledger;大段综合前先看 `summary`,避免丢失已完成分支。

### Phase 3:增量 QA(每个模块完成即跑,非最后一次)
`qa-verifier` 跑对应闸门;**真红**回对应实现者修;**假红**(本地 Redis / runner 假死)标注、不动测试。
- 触及 LLM / prompt / model registry / orchestrator / eval gold set 的改动,先跑 `python3 scripts/harness_llm_change_gate.py --path <changed-file>` 做零成本分类;命中高风险时必须跑 `python3 scripts/harness_llm_regression_gate.py --include-live-llm` 并把证据写入 Dossier/PR,CI 才允许设置 `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1` 通过 live-change 硬闸。

### Phase 4:安全评审(producer-reviewer)
触及敏感数据/用药/基因/安全规则/认证 → `safety-privacy-reviewer` 评审,阻断项整改 + 复审后才放行。

### Phase 5:交付 / 上线
- 源码分支/PR/CI 属于代码交付，不构成生产授权；是否提交、推送或合并仍按用户授权与
  `AGENTS.md` 执行，不能让 `release-engineer` 把 GitHub 状态解释成已上线。
- 上线交 `release-engineer` 时，`release.py`/`release.sh` plan/validate/publish 与所有
  production network observation 固定 BLOCK；只做本地 Metro/iOS Simulator/test（`npm
  run ios` 固定走 wrapper，不得向 npm/Expo 追加
  `--device`；wrapper 锁定 exact available Simulator UDID，物理 iOS repo CLI、连接/
  安装/验收冻结），或
  `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 的离线 metadata/report（无安装
  manifest、安装二维码或可安装承诺）。禁止自动 archive/export/signing/
  provisioning，尤其 `-allowProvisioningUpdates`。所有 OTA/rollback、server、Mobile production、Mac、ASC/App Review
  自动 release writer 与历史 release 旁路全部 exit 78；manual release Gate 记录 BLOCK 后
  停止，禁止 raw SSH 发布/CLI 兜底。server-local DB migration/setup/admin utility 只能进入
  独立 manual-admin 事件，绝不能被该自动 release 流程调用。
- 冻结原因是 same-UID writable repo bootstrap trust 无法闭合（Git replace/info
  attributes+filter/untracked import shadow/BASH_ENV/PYTHONPATH/sitecustomize），不是 CI
  是否为绿。解冻另立 dossier，并由 repo-external root-owned launcher 方案通过独立 G4。
- repo rc78 仅是 ordinary-invocation tombstone；Bash caller 可覆盖 `exit`/`builtin`。
  `deploy.sh`/`_run-mobile-tf.sh` legacy 必须 literal-false、语法级不可达且不得
  source/extract/eval；`release-dmg.sh` 全入口冻结，不能兼任 checker。

### Phase 6:验证 + 沉淀
公开未认证 HTTPS 或 offline evidence parser 可记录“观察到的现状”，但不能形成 G5/G6；
不得运行带凭证的 production smoke/network mode。冻结期间必须写
`G5=BLOCK`、`G6=BLOCK`、`App Store submission=BLOCK`，不得把协议测试或 local
结果写成 `shipped`/`complete`；把 trust-root 缺口沉淀回 Dossier 与对应 skill。

## 何时降级为单代理
单文件小修、纯文档、机械改动 —— 直接做或用单个 `Agent`,不必组队。
