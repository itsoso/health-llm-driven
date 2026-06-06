# 抗衰子系统:架构梳理与下一步演进(基于当前代码)

> 状态:架构综述 · 2026-06 · 基于 main(MVP #47-51 + Phase2 #52-55 + P3-3 #56 全部合并)
> 用途:把分散在 9 个 PR 里的抗衰能力,梳理成一张「它现在是什么 / 缺什么 / 往哪走」的图。
> 配套(本地):strategy-longevity-os / product-evolution-plan / design-longevity-mvp / plan-phase2 / design-phase2-hardware / plan-phase3。

---

## 1. 一句话现状

抗衰子系统 = **生物年龄(多维)的「测量 → 主动监测 → 干预 → 验证 → 群体学习」闭环**,已生产可用。
它不是新架构,是**复用既有 Agent-Native 四层(L1 采集 / L2 Twin / L3 专家 / L4 编排)**,只在每层加了抗衰特有的几块。

---

## 2. 子系统全景(基于真实文件)

```
                          ┌───────────────────────────── L4 编排 ──────────────────────────────┐
                          │ orchestrator → LongevitySpecialist (analyze_longevity 工具, flag)   │
                          └───────────────────────────────────────────────────────────────────┘
 L1 采集                      L2 Twin (15 分区)                 L3 专家                   闭环 / 群体
 ─────────────────────       ──────────────────────────        ─────────────────────     ────────────────────────
 体检 9 项血检 ─┐             labs.phenotypic_age ◄── phenoage   LongevitySpecialist        ProposedCard
 (medical_exams) │   builder   (_fill_phenoage)                  ├ 读 3 路生物年龄信号        → ActionCard
 Garmin VO2max ─┼─ _collectors physiological.vo2max_*           ├ _identify_drags          → outcome_grader
 (daily_health) │   _fill_*    (_fill_vo2max)                   ├ _compose_protocol         (metrics.fetch_
 DNAm 第三方   ─┘             epigenetic.* ◄── epigenetic_       │   (真实编排四件套)         phenotypic_age /
 (epigenetic_reports API)      report_service                   └ ProposedCard(12周N-of-1)    vo2max)
                                                                                            → ActionCard.outcome
   主动层 (Celery 周)                          群体层 (admin)                                      │
   ──────────────────                          ──────────────                                     ▼
   longevity_watch ── twin_snapshots 跨快照     longevity_cohort_service ◄────────────────  已评分 ActionCard
   diff → 推送 + audit(W6 eval)                 (去标识聚合) → /admin/longevity/cohort      (跨用户)
```

**核心算子 `phenoage.py`(纯函数,单一单位映射源)被三处复用**:builder 填 Twin、metrics 评分取值、cohort 聚合——杜绝单位手抄。

---

## 3. 文件清单(11 实现 + 6 测试)

| 层 | 文件 | 职责 |
|---|---|---|
| 算子 | `services/phenoage.py` | PhenoAge 纯函数 + `phenoage_from_labs` 共享映射 |
| L2 | `twin/builder.py` `_fill_phenoage`/`_fill_vo2max` | 填生物年龄 + 心肺信号入 Twin |
| L2 | `twin/schema.py` LabsContext/Physiological/EpigeneticState | phenotypic_age / vo2max_fitness_age / DNAm 字段 |
| L3 | `agents/longevity_specialist/` | 解读 3 路信号 + 编排四件套协议 + 提 N-of-1 卡 |
| 闭环 | `tasks/metrics/` fetch_phenotypic_age/vo2max/fitness_age | N-of-1 outcome 取值(已注册 + 方向) |
| 主动 | `services/longevity_watch.py` + `tasks/longevity_watch.py` | 周扫跨快照变化 → 推送(W1) |
| eval | `agents/audit.py` log_longevity_trigger | 主动触发埋点(W6) |
| 群体 | `services/longevity_cohort_service.py` + `api/admin_longevity.py` | 去标识群体证据(P3-3) |
| DNAm | `models/epigenetic_report.py` + `services/epigenetic_report_service.py` + `api/epigenetic_reports.py` | 第三方时钟摄入(W3) |
| 展示 | `mobile/components/home/BiologicalAgeCard.tsx` + `services/twinHelpers.ts`/`myProgress.ts` | 身体年龄卡 + 信任时刻对比 |

架构数字(当前 main):specialists 12 · twin 分区 15 · API 137 · services 190 · celery 52 · safety 51。

---

## 4. 能力边界:已落地 vs 仅设计

| 能力 | 状态 |
|---|---|
| PhenoAge 生物年龄(血检) | ✅ 生产 |
| VO2max / 体能年龄(心肺) | ✅ 生产 |
| DNAm 时钟摄入 + 交叉展示 | ✅ 生产(读+写) |
| 12 周 N-of-1(outcome=生物年龄) | ✅ 生产 |
| 主动监测 Agent(周) + eval 埋点 | ✅ 生产(周日 10:10) |
| 四件套真实编排协议 | ✅ 生产 |
| 群体证据(去标识) | ✅ 生产(admin) |
| 身体年龄卡 + 对比卡(mobile) | ✅ OTA 1.3.0 |
| 无感硬件(戒指/床垫) | 📐 仅设计(依赖商务) |
| Concierge / 商业化 / 退出叙事 | 📐 仅规划(依赖运营/供应链/合规) |
| eval **看板**(非仅埋点) | ⏳ P3-4 待做 |

诚实分级贯穿全程:PhenoAge/VO2max=validated · DNAm=experimental · 群体=observational;claim_boundary 随展示;伪科学红线。

---

## 5. 下一步产品演进方向(思考)

已走完「测量→验证」(MVP)、「主动多维」(Phase2)、「群体证据」(P3-3)。下一个**真正的产品跃迁**有三条候选,推荐第一条:

### ⭐ 方向一:数据飞轮 —— 群体证据 → 个性化干预推荐(强烈推荐,代码先行)
现状闭环是「开放环」:N-of-1 卡的干预靠规则/四件套通用建议,**没有用群体已验证的结果反哺个体推荐**。
- 把 P3-3 的群体证据(「哪类干预对哪类人降生物年龄最多」)接回 LongevitySpecialist 的提案:
  「和你相似的人做了 X,生物年龄平均降了 Y」→ 个性化排序 N-of-1 的干预选择。
- 这把产品从「track + verify」升级为「**track + verify + learn + recommend**」——**越多用户越聪明**的数据网络效应。
- 这是**估值/护城河的质变**:从"工具"变成"随规模复利的资产";也是退出叙事(P3-5)的引擎。
- 工程上纯代码可起步(cohort → 推荐权重),价值随用户量放大。**风险**:小样本/相关≠因果——必须标注样本量、不夸大成因果(沿用 observational 纪律)。

### 方向二:被动感知深化(无感硬件,Phase2 W5)
戒指/床垫让数据无感流入,提高依从率。**瓶颈是商务/选型,不是代码**(适配层已就绪)。
适合与方向一并行,但排期受商务约束。

### 方向三:Concierge 商业化(Phase3 P3-1/2)
把闭环产品化成高净值会员服务变现。**瓶颈是运营/供应链/合规**,代码只是末段。
是变现路径,但应在方向一(产品有效性证据更硬)之后,以更强底气定价。

### 取舍
**先方向一(飞轮,纯代码、复利资产、喂养所有后续)→ 方向二/三按商务节奏并行。**
飞轮一旦转起来:个体推荐更准 → outcome 更好 → 群体证据更强 → 推荐更准,这是抗衰 OS 区别于"又一个健康 App"的根本。

---

## 附:诚实声明
本文基于 2026-06 main 实际代码(9 PR 全合并)梳理,文件清单与数字经 check_doc_drift 核验。"仅设计/仅规划"项明确标注未落地及其依赖(商务/运营/合规)。方向一的飞轮需严守 observational 纪律(样本量 + 相关非因果),不得包装成临床因果证据。
