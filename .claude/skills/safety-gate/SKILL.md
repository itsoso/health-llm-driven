---
name: safety-gate
description: "敏感改动上线前的 producer-reviewer 安全 overlay。当改动碰用药、补剂、基因、化验、CGM/SpO2、提醒/通知、通用健康数据写路径、对外健康建议、隐私、加密、认证或 CORS 时必走；GO 才能继续，BLOCK 必须修复重审。"
---

# Safety Gate(敏感改动安全门)

本会话这套流程在 CGM(×2)、红线、R14(×2)、血氧(×3)每次都**抓到真 bug**。改动碰下列任一面,**部署前必走**。

这是 Router 选择后的**非 owning overlay**：可阻断当前 primary controller，但不得另建计划、批次、checkpoint、ledger 或“完成”状态；评审证据写回当前 Dossier/run。

## 触发条件(命中任一就走)

用药 / 补剂 / 基因 / 化验(labs)/ CGM / SpO2 血氧 / Safety Guardian 规则 / 提醒与通知(含推送文案和中断预算)/ 通用健康数据写路径 / 对外健康建议(剂量·减重·用药调整·趋势判读)/ 隐私 / 加密 / 认证 / CORS / 安全相关 Twin 字段。
(权威清单见 `AGENTS.md` §安全与 `docs/governance/security.md`。)

## 流程

1. **先把改动 commit 到本地**(reviewer 看 commit diff 最干净)。
2. **派独立 reviewer**:使用当前平台的只读审查能力或 `safety-privacy-reviewer` 角色,评审请求里给:
   - 要审的 commit hash + `git show <hash> -- <files>` 范围
   - 改动摘要 + 背景硬约束(如「只随访不开方」「Garmin 血氧不准」)
   - **明确让它重点审的安全问题**(漏报?假阳性?越界开方?绕过某条 CRITICAL 规则?时区/单位?)
   - 要 **GO / NO-GO** 明确裁定
3. **GO** → push + 部署(`backend-deploy`)。
4. **NO-GO** → 按阻断项**逐个修** + 补回归测试 → **重审**(用新的只读 reviewer 读当前固定 diff)。**反复 NO-GO 是正常的**(血氧改了三轮才 GO)。

## 为什么值得(本会话实战)

| 改动 | reviewer 抓到的真 bug |
|---|---|
| R14 跨数据源纠偏 | 对胃病/低BMI用户的**无门控减重建议**(有害)+ 我整改时引入的 `logger` NameError 把降级变 500 |
| CGM mmol 换算 | model_validator 绕过 `ge=20` 下限 + measured_at 默认 now 污染 batch 导入 |
| 血氧剔除 Garmin | 三条写入路径(pick_value / 兜底直查 / **SpO2Sample 主分支**)逐一漏 garmin 假值进夜间低氧 CRITICAL |

## 反模式(别做)

- ❌ 敏感改动直接 `deploy.sh -b` 不评审。
- ❌ NO-GO 后只修一条就部署(reviewer 常分轮揭露:修了表面,主路径还漏)。
- ❌ 测试假绿:测了没命中真实代码路径的分支(血氧那次主分支零覆盖 → 假绿)。补测试要覆盖**用户真实会走的路径**。
- ❌ 把"抑制告警"当小改动:从安全指标删源/降级,最危险是**漏报真急症**,必审方向。

> 非安全面的普通改动不用走这个,直接 `backend-deploy`。代码质量(非 bug)用 `/code-review` 或 `/simplify`。
