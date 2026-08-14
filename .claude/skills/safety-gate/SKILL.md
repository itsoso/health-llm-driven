---
name: safety-gate
description: "敏感改动上线前的 producer-reviewer 安全闭环。当改动碰 用药/基因/化验/CGM/SpO2血氧/Safety Guardian 规则/对外健康建议/加密/认证/CORS 时,部署前必走:派 safety-privacy-reviewer 评审,GO 才上线,NO-GO 修完重审。"
---

# Safety Gate(敏感改动安全门)

本会话这套流程在 CGM(×2)、红线、R14(×2)、血氧(×3)每次都**抓到真 bug**。改动碰下列任一面,**部署前必走**。

## 触发条件(命中任一就走)

用药 / 基因 / 化验(labs)/ CGM / SpO2 血氧 / Safety Guardian 规则 / 对外健康建议(剂量·减重·用药调整·趋势判读)/ 加密 / 认证 / CORS / 安全相关 Twin 字段。
(权威清单见 `AGENTS.md` §安全;CLAUDE.md「高风险必经」。)

## 流程

1. **先把改动 commit 到本地**(reviewer 看 commit diff 最干净)。
2. **派 reviewer**:用 Agent 工具 `subagent_type: safety-privacy-reviewer`,prompt 里给:
   - 要审的 commit hash + `git show <hash> -- <files>` 范围
   - 改动摘要 + 背景硬约束(如「只随访不开方」「Garmin 血氧不准」)
   - **明确让它重点审的安全问题**(漏报?假阳性?越界开方?绕过某条 CRITICAL 规则?时区/单位?)
   - 要 **GO / NO-GO** 明确裁定
3. **GO** → 只表示安全评审通过；源码交付按授权执行。自动 release entrypoint 仍冻结，交
   `backend-deploy` 记录 BLOCK，不得部署。
4. **NO-GO** → 按阻断项**逐个修** + 补回归测试 → **重审**(起新 reviewer 读当前 diff;SendMessage 不可用时直接新起一个)。**反复 NO-GO 是正常的**(血氧改了三轮才 GO)。

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

> 非安全面的普通改动不用走本安全 Gate；发布仍交 `backend-deploy` 做冻结裁决。代码质量
> (非 bug)用 `/code-review` 或 `/simplify`。
