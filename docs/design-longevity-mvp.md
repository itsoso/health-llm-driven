# 设计文档:抗衰 MVP —— 生物年龄闭环

> 状态:工程设计草案 · 2026-06
> 上游:`docs/strategy-longevity-os.md` §7(抗衰抓手)
> 本文定位:把"最该先抓的一个抓手"(PhenoAge + 生活方式四件套 + N-of-1)落成**可实现的工程设计**——真实接口、改动清单、边界、反馈环。
> 纪律:遵循 `feature-plan.md` 四问;遵循仓库已有的 `evidence_tier / claim_boundary` 诚实纪律;**伪科学红线不可妥协**。
>
> **CURRENT RELEASE OVERRIDE (2026-08-12):** 所有 repo 内自动远程/供应商 release
> entrypoint、本机 signing/install/automatic provisioning entrypoint 与所有 OTA/rollback
> channel writer 均冻结；EAS
> channel→branch 映射可能漂移或共用，preview/development 也
> 不是安全隔离。本文的 OTA/部署措辞只表示产品兼容性或历史规划，当前只可做本地
> Metro/iOS Simulator/test、只读 plan/proof 和
> `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 的离线 IPA metadata/report（无安装
> manifest、安装二维码或可安装承诺）。bare `--no-upload` 与自动
> archive/export/signing/provisioning 也冻结。`npm run ios` 固定走 Simulator wrapper，不得
> 向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator UDID，物理 iOS repo
> CLI、连接/安装/验收冻结。manual Gate 必须 BLOCK/STOP；解冻须新 dossier、
> repo-external root-owned launcher、固定解释器、
> `env -i`、repo-external canonical tree、source/artifact/recovery proof 与新独立 G4。

---

## 0. 一句话

**用一张普通体检报告算出"身体年龄"(PhenoAge),用已有的生活方式专家做 12 周 N-of-1 干预,再算一次,产出"你年轻了 X 岁"的可验证对比卡——零新硬件,~80% 代码已有。**

---

## 1. 四问(feature-plan)

**1) 用户价值**:抗衰人群想知道"我身体几岁、能不能变年轻"。现状只能花钱测一次 DNAm 时钟拿一份 PDF(贵、一次性、无法证明干预有用)。做到极致 = 从"一次性 PDF"变成"每个体检周期自动更新 + 干预后真实下降的曲线"。

**2) 边界(不做)**:① 不自建甲基化测序/实验室(接第三方,见战略 §4);② MVP 不做硬件接入(戒指/床垫留 Phase 2);③ 不开方、不诊断 Tier 3 药物;④ 不做高净值 concierge(Phase 3)。

**3) 最简实现**:PhenoAge 是一个**纯函数**(9 项血检 + 年龄 → 表型年龄)。复用已有 `medical_exams` 解析 + `episodes`/`personal_outcome` 闭环 + 4 个生活方式 specialist。核心新代码集中在:① PhenoAge 计算器 ② LongevitySpecialist ③ labs 补 7 个字段。

**4) 风险**:① labs 字段扩展(schema 改动,见 §3.2);② PhenoAge 系数必须对齐论文 + golden test(不许我手抄系数当成功);③ 伪科学合规(claim_boundary);④ doc-drift(新 specialist → 更新 EXPECTED + ARCHITECTURE)。

---

## 2. 现状盘点(已核实代码,2026-06)

| 资产 | 位置 | 状态 |
|---|---|---|
| 生物年龄分区雏形 | `app/twin/schema.py` `EpigeneticState`:`biological_age` / `biological_age_delta_years` / `pace_of_aging` / `clock_type` / `vendor` / **`evidence_tier`+`claim_boundary`** | ✅ 已有(专用于 **DNAm 甲基化时钟**,experimental/low) |
| 体检解读 | `app/api/medical_exams.py` → `exam_explain_service.build_exam_explain` | ✅ 已有(建 Twin 钩子) |
| 化验上下文 | `LabsContext`:已有 glucose / creatinine / 肝酶 / 血脂 / eGFR / 尿酸 | ⚠️ **缺 PhenoAge 7 项**:albumin / CRP / 淋巴% / MCV / RDW / ALP / WBC |
| N-of-1 闭环 | `app/api/episodes.py`(list/get/feedback)+ `app/api/personal_outcome.py`(timeline/impact/scorecard) | ✅ 已有 |
| 生活方式专家 | `recovery_coach` / `fuel_strategist` / `movement_coach` / `mental_health_companion` | ✅ 已有(四件套对口) |
| 专家工具化 | `app/services/specialist_tools.py`(PR #46,flag 门控,`analyze_*`) | ✅ 已有 |
| specialist 注册 | `app/orchestrator/specialists.py` `_build_registry()` | ✅ 已有(新增需在此注册 + doc-drift) |
| 专家产出结构 | `app/orchestrator/schema.py` `SpecialistFinding`(specialist_name/summary/findings/evidence_refs) | ✅ 已有 |

> **关键区分**:`EpigeneticState` = 甲基化时钟(贵、第三方、experimental、不证明短期干预)。**PhenoAge = 血检表型年龄(便宜、可自算、适合追踪短期变化)**。二者互补,**不要混进同一字段**。

---

## 3. 核心设计 ①:PhenoAge 计算器

### 3.1 算法
PhenoAge(Levine et al., 2018, *Aging*)= 9 项血检 + 实足年龄 → 线性组合 → Gompertz 死亡风险 → 反解成"表型年龄(岁)"。

输入 9 项:白蛋白(g/L)、肌酐(μmol/L)、血糖(mmol/L)、CRP(mg/dL, 取 ln)、淋巴细胞百分比(%)、MCV(fL)、RDW(%)、碱性磷酸酶 ALP(U/L)、白细胞 WBC(10⁹/L)+ 实足年龄。

> ⚠️ **实现纪律(不假装精确)**:系数与单位换算**必须对齐 Levine 2018 原文**,并写一个 **golden test**——用论文/公开实现给出的样例输入跑出已知 PhenoAge 输出,误差 < 0.1 岁才算通过。**绝不把我凭记忆写的系数当成已验证。** 缺任一输入项 → 返回 `None` + 标 `insufficient_inputs`,不猜算。

### 3.2 数据来源与 labs 缺口
- 已有:glucose、creatinine(`LabsContext`)
- **需补 7 字段到 `LabsContext`**:`albumin` / `crp` / `lymphocyte_pct` / `mcv` / `rdw` / `alp` / `wbc`
- 解析侧:`exam_explain_service` / 体检 OCR 解析需能抽出这 7 项(常规血常规+生化都含,数据可得性高)

### 3.3 放哪(避免 doc-drift)
PhenoAge 是**血检衍生**,放进 `LabsContext` 作派生字段,**不新建分区**(避免 Twin partition 计数变化触发 doc-drift):
```
LabsContext 追加:
  phenotypic_age: Optional[float]            # PhenoAge 结果
  phenotypic_age_delta_years: Optional[float] # = phenotypic_age - 实足年龄
  phenotypic_age_inputs_complete: bool        # 9 项是否齐
  evidence_tier: str = "validated"            # 区别于 epigenetic 的 experimental
  claim_boundary: str                         # 沿用诚实纪律,见下
```
`claim_boundary` 文案(沿用 `EpigeneticState` 风格):
> "PhenoAge 是基于血检的死亡风险代理指标,反映当前生理状态,不等于真实生物学衰老速度;用于追踪可逆的生理改善,不作疾病诊断。"

计算时机:`twin/builder.py` 聚合 labs 后调用 `compute_phenoage(labs, age)` 填充。

---

## 4. 核心设计 ②:LongevitySpecialist

新建 `app/agents/longevity_specialist/`,实现 Specialist Protocol(对齐现有 `recovery_coach`):

```
class LongevitySpecialist:
    name = "longevity"
    def applies_to(self, intent, twin) -> bool:
        # intent 含 longevity/抗衰/生物年龄, 或 labs.phenotypic_age 存在
    def run(self, twin, context) -> SpecialistFinding:
        # 读: labs.phenotypic_age(+delta) / epigenetic / body_composition / physiological(VO2max代理/HRV/睡眠)
        # 出: summary="你的身体年龄 47(实足 42, +5);主要拖累:代谢+睡眠"
        #     findings=[{label, value, evidence_tier}], evidence_refs=[Levine2018...]
        # 干预建议: 委托四件套专家(Movement/Fuel/Recovery/Mental), 不重复造科学
        # Tier 分级: Tier1 生活方式优先; Tier2 补剂标"功能改善"; Tier3 药物只提示+持牌
```
注册:`_build_registry()` 追加 `LongevitySpecialist()`(放在 LongitudinalAnalyst 附近)。
工具化:`specialist_tools.py` 的 `SPECIALIST_TOOLS` 加 `analyze_longevity`(沿用 PR #46,flag 门控)。

---

## 5. 核心设计 ③:N-of-1 闭环复用(outcome = 生物年龄)

不新建闭环,**复用** `episodes` + `personal_outcome`:
- Episode 的 outcome 指标支持 `phenotypic_age_delta`(周期前 vs 复检后)
- `personal_outcome` 的 timeline/impact 能展示生物年龄随干预事件的变化
- 因果归因复用 `longitudinal_analyst`("这 12 周 −2.1 岁,主要来自睡眠 +运动")

---

## 6. 核心设计 ④:Safety Guardian 抗衰规则

`app/agents/safety_guardian/rules/` 新增抗衰规则(`@register`):
- Tier 3 药物提示:雷帕霉素 / 二甲双胍(off-label)/ senolytics → 风险提示 + "请线下持牌医生",**不阻断用户知情,但绝不背书**
- 补剂相互作用沿用已有 dsi 规则(NAD/鱼油等)
> 新规则文件 → `engine.py` `_load_rule_modules()` import + `check_doc_drift.py` EXPECTED 同步。

---

## 7. 对比卡 UI(mobile 优先)

复用 `mobile/`:首页加"身体年龄卡"——大数字(47)+ 实足(42)+ delta(+5)+ 趋势 sparkline + claim_boundary 小字。周期复检后弹"你年轻了 X 岁"对比卡(信任时刻)。纯 RN；当前只做本地验证，OTA writer 冻结。

---

## 8. ASCII 数据流

```
体检报告上传 (mobile)
    ↓ POST /api/v1/medical-exams (已有)
exam_explain_service 解析 9 项血检 (改造: 补抽 7 项)
    ↓
twin/builder.py 聚合 labs → compute_phenoage(labs, age)  ← 新建纯函数
    ↓ 写入 LabsContext.phenotypic_age (+claim_boundary)
LongevitySpecialist.run(twin)  ← 新建, 读 phenoage+四件套
    ↓ SpecialistFinding(summary/findings/evidence_refs)
启动 Episode (N-of-1, outcome=phenotypic_age_delta)  ← 复用 episodes.py
    ↓ 12 周生活方式干预 (Movement/Fuel/Recovery/Mental 专家)
复检 → 再算 PhenoAge → personal_outcome impact + 对比卡  ← 复用
    ↓
mobile 首页"身体年龄卡" (本地验证；OTA 冻结)
```

---

## 9. 改动清单(按文件)

| 文件 | 改动 | 类型 |
|---|---|---|
| `app/services/phenoage.py` | `compute_phenoage(labs, age)` 纯函数 + 单位换算 | 🆕 |
| `tests/test_phenoage.py` | **golden test**(对齐 Levine 2018 样例)+ 缺值兜底 | 🆕 |
| `app/twin/schema.py` `LabsContext` | 补 7 输入字段 + 4 派生字段(phenotypic_age 等) | 🔧 |
| `app/twin/builder.py` | labs 聚合后调用 compute_phenoage 填充 | 🔧 |
| `app/services/exam_explain_service.py`(或解析层) | 补抽 albumin/CRP/淋巴%/MCV/RDW/ALP/WBC | 🔧 |
| `app/agents/longevity_specialist/` | LongevitySpecialist 实现 | 🆕 |
| `app/orchestrator/specialists.py` | 注册 LongevitySpecialist | 🔧 |
| `app/services/specialist_tools.py` | 加 `analyze_longevity`(flag 门控) | 🔧 |
| `app/agents/safety_guardian/rules/longevity.py` | Tier 3 药物提示规则 | 🆕 |
| `app/agents/safety_guardian/engine.py` | import 新规则模块 | 🔧 |
| `scripts/check_doc_drift.py` + `docs/ARCHITECTURE.md` | specialist 数 11→12、安全规则数同步 | 🔧 |
| `tests/test_specialists.py` | LongevitySpecialist 单测 | 🔧 |
| `mobile/` 首页 | 身体年龄卡 + 对比卡(本地验证；OTA 冻结) | 🆕 |

> 复杂度预算:每个新文件 < 500 行;phenoage.py 应 < 120 行。

---

## 10. 分期(增量交付,每步可独立验证)

- **Step 1(后端纯算,反馈环最短)**:`phenoage.py` + golden test。`pytest tests/test_phenoage.py` 秒级绿 = 抓手成立。
- **Step 2**:labs 7 字段 + builder 填充 + LongevitySpecialist + 注册 + doc-drift。`GET /twin/me` 能看到 phenotypic_age。
- **Step 3**:Episode outcome=phenotypic_age_delta 串通 + 对比卡 UI（本地 Metro/Simulator 验证）。
- **Step 4(Phase 2)**:Safety 抗衰规则 + 硬件接入 + 主动 Agent。

---

## 11. 边界与不做(防范围蔓延)
- ❌ 不自建甲基化时钟(EpigeneticState 接第三方即可)
- ❌ 不在 MVP 做硬件(戒指/床垫/CGM Phase 2)
- ❌ 不开方/不诊断 Tier 3 药物
- ❌ 不动现有 `EpigeneticState` 语义(PhenoAge 独立字段)
- ❌ 不为抗衰分叉 API(统一 `/api/v1/*`)

---

## 12. 风险与合规
- **PhenoAge 系数**:不许凭记忆当真,**golden test 是硬门**。
- **伪科学红线**:只用有证据的 biomarker;PhenoAge 标 `validated`、DNAm 标 `experimental`;claim_boundary 强制随结果一起展示;**绝不宣称"逆龄/治疗"**。
- **schema 改动**:LabsContext 加字段全是 Optional,向后兼容;无破坏性 migration(Twin 是运行时聚合,非持久表)。
- **doc-drift**:新 specialist/规则 → 同 PR 更新 `check_doc_drift.py` EXPECTED + `ARCHITECTURE.md`,否则 CI 挂。
- **auth/隔离**:沿用现有 JWT + user 隔离,PhenoAge 走 `build_twin(db, user_id)`,不跨用户。

---

## 13. 反馈环
- Step 1:本地 `pytest`,秒级(纯函数)。
- Step 2-3 后端:`pytest` + `uvicorn` 本地打 `/twin/me`。
- Mobile:纯 RN/TS、无 native 改动也只用本地 Metro/iOS Simulator/test；`npm run ios`
  固定走 Simulator wrapper，不得向 npm/Expo 追加 `--device`；wrapper 锁定 exact available
  Simulator UDID，物理 iOS repo CLI、连接/安装/验收冻结；所有
  OTA/rollback channel 与 production native writer 均冻结，到 manual Gate 记录 BLOCK。

---

## 附:诚实声明
本设计基于 2026-06 对本仓库代码的实际核实(EpigeneticState / episodes / personal_outcome / medical_exams / LabsContext / specialists registry 均已逐一确认存在或缺失)。PhenoAge 算法引用 Levine 2018,**实现时必须以原文系数 + golden test 为准**,本文给出的输入清单仅供设计,不作为可直接编码的精确公式。证据分级与 claim_boundary 沿用仓库既有诚实纪律。落地前医疗合规边界需专业法务确认。
