# 抗衰方向 Phase 2 规划:从"单点身体年龄"到"主动、多维、可验证"

> 状态:规划草案 · 2026-06
> 上游:`docs/strategy-longevity-os.md`(§10 演进路线)、`docs/design-longevity-mvp.md`(MVP 设计)
> 承接:抗衰 MVP(#47-51)已**全栈上线**(后端 + OTA + Web)。本文规划 MVP 之后的下一阶段。
> 纪律:软件优先、低成本高证据优先;伪科学红线不可妥协;主动推送守"打扰预算"。

---

## 0. 现状(MVP 已上线,诚实基线)

已生产可用的北极星闭环:
```
体检 9 项血检 → PhenoAge 身体年龄 → LongevitySpecialist 解读 →
12 周 N-of-1 卡(outcome=phenotypic_age)→ 复检自动评分 → 首页「47→44 年轻3岁」
```
**已有但 MVP 没用满的资产**(Phase 2 直接吃):
- `physiological.vo2max_running/cycling` + Garmin `vo2max_fitness_age` —— 第二个生物年龄信号,已在 Twin,**零采集成本**
- `daily-anomaly-check` 等成熟 Celery 定时任务 + `notifications` 服务 —— 主动 Agent 的现成载体
- `epigenetic_report` model + `epigenetic_report_service` + builder `_fill_epigenetic` —— DNAm 时钟摄入链**已搭好**,只差上传入口
- `device_adapters/` —— 可穿戴接入点已存在

---

## 1. Phase 2 目标(绑北极星 + 估值杠杆)

MVP 证明了"能算、能验证一次"。Phase 2 要让它**主动、多维、可信地规模化**:

| 目标 | 对应北极星/杠杆 |
|---|---|
| Agent **主动**盯生物年龄(不靠用户问) | 留存 + 打扰预算下的 DAU |
| 生物年龄**多维**(PhenoAge + VO2max + DNAm 交叉) | 可信度 ↑ → 反伪科学护城河 |
| 闭环**可观测**(主动推送命中率/误报) | 规模化前提(RFC 方向九) |
| 无感硬件喂数据 | /goal「硬件无侵入感佩戴」 |

北极星不变:**完成 ≥1 个 12 周 N-of-1 且生物年龄改善的用户数**;Phase 2 加一条过程指标:**主动触发→建卡→被接受率**。

---

## 2. 工作流(workstreams)

> ✅ 已有雏形 / 🔧 扩展 / 🆕 新建 · 标优先级 P0-P2 · 标是否纯代码

### W1 · 主动化:事件驱动的生物年龄 Agent(P0,纯代码)
新血检入库 → 重算 PhenoAge → 对比上次 → **回退则预警、改善则庆祝**,自动建卡 / 推送。
- 🔧 复用 `daily-anomaly-check` 的 Celery + `notifications` 模式
- 🆕 `tasks/longevity_watch.py`:检测 `phenotypic_age` 跨快照变化(需落 twin_snapshots —— 表已存在 `20260603_140000_create_twin_snapshots`)
- 对应 RFC 方向三(事件驱动主动 Agent)
- **守打扰预算**:回退≥2岁或周期到期才推,默认沉默

### W2 · 第二抓手 VO2max / Fitness Age(P0,纯代码,最高性价比)
VO2max 是全因死亡率最强单一预测因子,且**已在 Twin、零采集成本**。
- 🔧 LongevitySpecialist 读 `vo2max_running` + Garmin `vo2max_fitness_age`,与 PhenoAge 并列成"两个生物年龄信号"
- 🔧 metrics 加 `vo2max` / `fitness_age` 作 N-of-1 outcome(运动干预最易见效)
- 证据强、免费、运动可逆 —— Phase 2 第一刀就该做

### W3 · DNAm 时钟接入闭环(P1,代码为主 + 第三方)
摄入链已搭好(model+service+builder),补"进得来 + 展示得出"。
- ✅ `epigenetic_report_service` 已有 → 🆕 补上传 API + mobile 入口(用户传第三方时钟 PDF/报告)
- 🔧 PhenoAge(validated)× DNAm(experimental)交叉展示,**严守 evidence_tier 分级**,不混淆
- 不自建时钟(战略 §4 的 2.78% 教训)

### W4 · 干预深化:N-of-1 从"委托文字"到"真实协议"(P1,纯代码)
现在 LongevitySpecialist 的"委托四件套"只是 findings 里的文字。
- 🔧 让它真正**编排** Recovery/Fuel/Movement/Mental 输出一份整合的 12 周抗衰协议(睡眠/运动/营养/压力具体处方),挂在 N-of-1 卡上
- 复用 orchestrator 的 specialist 协作(已有 readiness_zone 传递先例)

### W5 · 无感硬件接入(P2,非纯代码 —— 依赖 BD/采购)
- 🆕 贴牌戒指/床垫 → `device_adapters/` → Twin(`physiological`/睡眠/HRV)
- **依赖**:选型 + 贴牌商务 + SDK 对接,工程只是其中一段;不自建硬件(战略 §5)
- 先验证依从率,再谈规模

### W6 · eval / 可观测(P0 前置,纯代码)
主动 Agent(W1)扩规模**前必须**先能度量,否则骚扰用户不自知。
- 🆕 主动推送命中率 / 误报率 / 接受率埋点;闭环评分准确率
- 对应 RFC 方向九(eval/observability,方向一/三的前置)

---

## 3. 排序与依赖

```
第一批 (Phase 2 MVP, 纯代码高性价比):
  W2 VO2max(免费高证据) ‖ W6 eval 骨架 → 然后 W1 主动化(靠 W6 才能不扰民)
第二批:
  W4 干预深化(让协议真实) → W3 DNAm 闭环(摄入链已就绪)
第三批 (慢, 非纯代码):
  W5 无感硬件(BD 驱动, 工程配合)
```
原则:**软件优先、证据强优先、能复用现有基础设施优先**。硬件最慢且依赖商务,不卡软件迭代。

---

## 4. 风险与边界

| 风险 | 缓解 |
|---|---|
| 主动推送扰民 | 默认沉默 + 打扰预算 + 仅显著事件触发(W1/W6 联动) |
| DNAm 被当成铁证 | 严守 evidence_tier:PhenoAge=validated / DNAm=experimental,claim_boundary 随展示 |
| VO2max 设备估算偏差 | 标注来源与可信度,多日均值,不单点下结论 |
| 硬件依从率低 / 合规 | 先小样本验依从再规模;贴牌守医疗器械/数据合规 |
| 伪科学红线 | 只上有证据抓手;干预 Tier 分级(强证据=生活方式,药物仅提示) |
| 多信号互相矛盾 | 明确"PhenoAge 与 VO2max 与 DNAm 互补不替代",冲突时如实呈现不强行合一 |

---

## 5. 第一刀(Phase 2 的最小可落地批次)

**建议第一个 PR 批次 = W2(VO2max 第二抓手)+ W6 eval 骨架,随后 W1 主动化:**
1. W2:LongevitySpecialist 读 VO2max/fitness_age,metrics 加 vo2max outcome —— 纯代码、免费、证据强、当天可验证
2. W6:给主动 Agent 先建埋点骨架(命中/接受率)
3. W1:`longevity_watch` Celery 任务(基于 twin_snapshots 跨快照对比)→ 主动预警/庆祝 + 建卡

理由:全部纯代码、全部复用已上线基础设施、全部不碰硬件/商务依赖,反馈环最短;把 MVP 的"被动单点"升级成"主动多维",直接抬北极星过程指标。

---

## 附:诚实声明
本规划基于 2026-06 对已上线 MVP 与代码资产的实际核实(VO2max 字段、Celery/notifications、epigenetic_report 链、device_adapters、twin_snapshots 表均已确认存在)。W5 硬件含**非代码依赖**(商务/采购),不应按纯工程排期。证据分级与 claim_boundary 沿用仓库既有诚实纪律;伪科学红线为本方向生死线。落地前医疗合规边界需专业法务确认。
