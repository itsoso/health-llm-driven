# 用药自动驾驶 (Medication Autopilot) — 让"按方吃药"变成无脑

> **状态**: 设计草案 (2026-06-14)
> **触发场景**: 创始人自身案例 —— 胃溃疡 / 幽门螺杆菌根除,需同时吃 3–4 种药,不同药相对吃饭的时点不同、一天多次、14 天后疗程还要换方。"怎么才能最无脑吃?"
> **一句话**: 把医生开的复杂用药方案,一次性"录入"成一条可执行的时间线,之后系统全程接管 —— 该吃什么、何时吃(相对吃饭)、吃了没、疗程到点自动换方、结束自动约复查、引入新药先过相互作用闸门。用户只需对一条提醒点一下"已吃"。
>
> **CURRENT RELEASE OVERRIDE (2026-08-12):** 所有 repo 内自动远程/供应商 release
> entrypoint、本机 signing/install/automatic provisioning entrypoint 与所有 OTA/rollback
> channel writer 均冻结。EAS
> channel→branch 映射可能漂移或共用，preview/development
> 不是安全隔离；当前只做本地 Metro/iOS Simulator/test、只读
> proof 和 `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>`。bare `--no-upload` 与自动
> archive/export/signing/provisioning 也冻结。`npm run ios` 固定走 Simulator wrapper，不得
> 向 npm/Expo 追加 `--device`；wrapper 锁定 exact available Simulator UDID，物理 iOS repo
> CLI、连接/安装/验收冻结。本文 rollout 中任何人工 Gate 都表示 BLOCK/STOP，
> 不授权 EAS/ASC、server deploy、release helper 或 raw SSH 发布。server-local admin utility 只可进入独立获权事件，
> 不得被本自动 release 流程调用。

---

## 0. 核心定位(安全边界,先钉死)

**本系统是"用药执行 / 依从"工具,不是"开方 / 用药建议"工具。**

- 方案来自**医生处方**。用户(或拍处方 OCR / 选模板脚手架)把"医生开了什么"录进来,系统负责让"按这个吃"变无脑。
- 系统**永不**自动决定剂量、换药、加药。模板只是"录入脚手架"(帮你 30 秒把铋剂四联录全,而不是一个个手填 12 个时点),录完必须用户确认"这就是医生开的"。
- 引入任何新药 → **强制过 SafetyGuardian 全量 DDI/PGx/DSI 校验**(用户已在吃 12 种药,含长期 PPI),有 CRITICAL 阻断并提示就医,绝不静默放行。

这条定位决定了下面所有设计:**无脑的是"执行",不是"决策"。**

---

## 1. 四问

### 1.1 用户价值 (Why)
- **谁的什么问题**: 任何需要"多药 + 复杂时点 + 分阶段疗程"的人(胃溃疡根除是最典型,慢病联合用药同理)。痛点不是"忘记吃药"(普通提醒已解决),而是:
  1. **记不住哪个药相对吃饭什么时候吃** —— PPI 要**空腹/饭前 30 分钟**,抗生素要**饭后**,铋剂要**饭前**。同一个早晨这三件事时点都不同。
  2. **疗程会变** —— 根除期(14 天,4 种药)结束后转愈合期(4–8 周,只留 PPI 1 种)。手动维护这个切换极易出错。
  3. **漏服后果不对称** —— 抗生素漏服直接拉低根除率甚至诱导耐药,不能随便补;PPI 漏服影响小。普通提醒不区分。
- **现在怎么绕**: 手机闹钟设 6 个 + 自己记小本子 + 拿一个塑料周药盒手动分装。闹钟不认"饭前饭后",换方要重设全部闹钟,漏没漏只能靠回忆。
- **做到极致的量化改变**: 从"每天 6 次自己判断该吃哪个 + 每周重排闹钟"→ **每天只对提醒点 N 次"已吃",疗程切换/复查/安全检查全自动**。规划动作从 N 次/天 → 0。

### 1.2 边界 (What NOT)
- **不做**自动开方、自动调量、自动换药(安全红线,见 §0)。
- **不做**自研智能硬件。硬件走"软件智能 + 哑药盒"或"集成第三方 BLE 药盒",不造盒子(见 §4)。
- **不做** Android 全套(现有 `medicationReminders.ts` Android 返回 0)。本期 iOS 优先,Android 本地通知补到能用即可。
- **本期暂不做**:多用户(家人)代管用药、药房自动续方下单、保险/医保对接 —— 留后续。

### 1.3 最简实现 (How — 复用 > 新建)
仓库现状(Explore 实测,见附录 A)已覆盖大部分。本设计**只补 4 处**,其余复用:

| 能力 | 现状 | 本期动作 |
|---|---|---|
| Medication / MedicationLog 模型 | ✅ 有,缺时点关系/疗程 | **补字段**(见 §2) |
| 提醒扫描 `scan_medication_reminders` (每分钟) | ✅ 有 | 复用,扩成"相对吃饭"语义 |
| 依从日志 MedicationLog.status | ✅ 有 (taken/skipped/delayed) | 复用,加通知一键确认 |
| Twin medication 分区 | ✅ 有 | 加 `course_phase` / `days_left` |
| 疗程→复查闭环 `medication_course_service` | ✅ 有 (PPI→胃镜映射) | 复用,接 §3 阶段机 |
| DDI/PGx 安全规则 | ✅ 15+ DDI / 12 基因 | **补长期 PPI 规则 + 引入即校验** |
| 前端/移动端用药页 | ✅ 有 | 加"方案模板"录入 + 时间线视图 |
| Daily Plan 集成 | ❌ 0% | **把当日用药条目注入 DailyOperatingPlan** |

四处真正的新建:① 模型字段(`timing_relation` + `MedicationRegimen` 疗程/阶段);② 方案模板引擎;③ 相对吃饭的智能提醒(耦合现有饮食打卡);④ 长期 PPI 安全规则 + 引入即校验。

### 1.4 风险 (What could go wrong)
- **Schema 改动**: Medication 加列 + 新增 MedicationRegimen 表 → 手写 SQL 迁移(无 Alembic),`ADD COLUMN ... DEFAULT` 向后兼容,旧药记录 `timing_relation=NULL` 当"无要求"。
- **安全边界**: 引入新药不过 DDI 校验 = 出人命级风险。校验必须是**写入前的硬闸门**,不是事后提醒。
- **Native 依赖**: iOS 通知 action button(一键"已吃")属通知 category 配置，需要原生
  候选(改 `app.json` / 通知类目)。纯排程逻辑/UI 只做本地验证；所有 OTA/rollback channel
  与 production native writer 均冻结，到人工 Gate 记录 BLOCK。
- **复杂度预算**: 新代码拆分到 `medication_regimen_service.py` + `regimen_templates.py`,不堆进现有文件;Medication 模型加字段不算扩文件。
- **doc-drift**: 新增 model(MedicationRegimen)+ 可能新增 safety rule(长期 PPI)→ 同 PR 更新 `scripts/check_doc_drift.py` EXPECTED + ARCHITECTURE.md。

---

## 2. 数据模型补强

现有 `Medication` 缺两类关键信息,这是"无脑"的硬前提:

### 2.1 给 Medication 加"相对吃饭的时点"
```python
# backend/app/models/medication.py — ADD COLUMN
timing_relation: str | None   # 'before_meal_30' | 'before_meal' | 'with_meal'
                              # | 'after_meal' | 'empty_stomach' | 'bedtime' | 'anytime'
meal_anchor: str | None       # 'breakfast' | 'lunch' | 'dinner' | None(任意餐)
spacing_min: int | None       # 与其他药/食物的最小间隔分钟(如铋剂与奶制品)
regimen_id: int | None        # 外键 → MedicationRegimen(属于哪个疗程方案)
```
> 没有 `timing_relation`,提醒只能报"该吃 X 药"却说不出"空腹还是饭后",用户还得自己查 —— 不算无脑。

### 2.2 新增 MedicationRegimen(疗程 / 阶段)
H. pylori 根除是**多阶段**:根除期(14d,4 药)→ 愈合期(4–8w,1 药)。一个疗程串起多个阶段,每阶段一组药 + 时点。

```python
# backend/app/models/medication_regimen.py — NEW
class MedicationRegimen:
    id; user_id
    name              # "幽门螺杆菌根除·铋剂四联 + PPI 愈合"
    source            # 'template:hp_bismuth_quad' | 'ocr_prescription' | 'manual'
    template_id       # 若来自模板
    status            # 'active' | 'completed' | 'paused'
    current_phase     # 当前阶段序号
    phases: JSON      # [{name, duration_days, meds:[{drug,dose,freq,timing_relation,meal_anchor,times}], transition}]
    started_on; expected_end_on
    review_on_complete  # 复查项(接 medication_course_service:PPI→胃镜)
```
> 阶段切换 = "到第 15 天,自动停 3 种药、PPI 改 1 次/天、推一条'进入愈合期'"。这是手动闹钟绝对做不到、最容易出错的地方,正是系统价值所在。

---

## 3. 方案模板引擎(30 秒录入,而非手填 12 个时点)

`backend/app/services/regimen_templates.py`(纯数据 + 实例化函数,**不含用药建议**)。

模板是"录入脚手架":医生说"标准铋剂四联 14 天",用户选这个模板 → 系统弹出预填好的方案 → 用户核对剂量(医生可能调过)→ 确认 → 一键实例化成 MedicationRegimen + 全部 Medication + 排程 + 阶段切换 + 复查。

**示例模板(胃溃疡 / Hp 根除,以医生处方为准)**:
```
hp_bismuth_quad_14d:
  阶段1 "根除期" (14天):
    - PPI            (如雷贝拉唑 10–20mg)  ×2/日  早晚 餐前30分钟
    - 铋剂           (枸橼酸铋钾 220mg)    ×2/日  早晚 餐前30分钟
    - 阿莫西林        (1000mg)             ×2/日  早晚 餐后
    - 克拉霉素        (500mg)              ×2/日  早晚 餐后   ⚠ CYP3A4 强抑制 → 引入即查
  阶段2 "愈合期" (4–8周):
    - PPI            (如雷贝拉唑 10–20mg)  ×1/日  早 餐前30分钟
  完成动作: 约消化内科 + 胃镜/呼气试验复查(复用 medication_course_service)
```
> "三种药"的三联变体(去铋剂)同样是一个模板;用户当下到底几种由医生定,模板只是把常见组合预填好省录入。

实例化流程:
```
用户选模板 / 拍处方OCR
    ↓
预填方案卡(剂量可改)→ 用户核对确认"这是医生开的"
    ↓
[硬闸门] SafetyGuardian 跑 DDI/PGx/DSI:新药 × 已有12种药
    ├─ CRITICAL(如克拉霉素×他汀)→ 阻断,提示就医,不写入
    └─ 通过/有提示 → 继续
    ↓
建 MedicationRegimen + N 条 Medication(带 timing_relation)+ 排程
    ↓
medication_course_service 物化复查 ReviewSchedule
```

---

## 4. 硬件策略:软件智能 + 哑药盒(分层,不造盒子)

用户问的"药盒/自动设定好每周要吃的药的药盒"分三层落地,**本期主打 L0+L1,L2 留接口**:

| 层 | 形态 | 成本 | 无脑度 | 本期 |
|---|---|---|---|---|
| **L0** 纯软件 | 不用盒子,App 全程相对吃饭提醒 + 一键确认 + 自动换方 | ¥0 | ★★★★ | ✅ MVP |
| **L1** 哑药盒 + 软件 | 普通 7×3 格周药盒(¥20)。App 一周一次生成**分装图**(哪格放哪些药),填一次管一周;之后软件接管每次提醒/确认 | ¥20 | ★★★★ | ✅ |
| **L2** 智能药盒 | 第三方 BLE 智能药盒/自动分药机(如有品类),**开盖即回写 adherence**,真零点击 | ¥200+ | ★★★★★ | 🔌 留集成接口,不自研 |

**关键判断**: L0 已经拿下 80% 的"无脑"——因为复杂的从来不是"physically 拿药",而是"判断现在该吃哪个 + 没记错吃没吃 + 疗程别搞错"。这些 L0 全包了。L1 只解决"一周分装一次"的物理麻烦,用一张 App 生成的分装图(而不是智能硬件)就够。L2 是锦上添花,通过标准 BLE/HTTP 回写 `MedicationLog`,不绑死任何厂商。

> 反模式警惕:不要为了"看起来酷"先做 L2 智能硬件集成。先把 L0 软件做到真无脑,这是反馈环最短、覆盖最广、零硬件依赖的路径。

---

## 5. "无脑"的核心:相对吃饭的智能提醒(复用现有饮食打卡)

普通提醒是"08:00 提醒吃药"。但 PPI 要饭前 30 分钟、抗生素要饭后 —— **系统不知道用户几点吃饭,固定 HH:MM 就会错**。本平台已有**饮食打卡**,这是别家没有的杠杆:

```
策略A(学习型,默认): 从历史饮食打卡学习习惯三餐时间
    → 早餐通常 7:30 → PPI 提醒定在 7:00(饭前30min)
    → 抗生素提醒定在"早餐打卡后"触发

策略B(事件型,最准): 用户记早餐 → 系统立即:
    ① "刚吃完早饭,该吃阿莫西林+克拉霉素了,各1粒(饭后)"
    ② 若 PPI 该饭前吃却没记录 → "PPI 是饭前吃的,刚才吃了吗?"补救确认

策略C(兜底): 无饮食数据 → 退回固定 reminder_times(现有行为)
```

提醒文案带**完整执行指令**,用户零判断:
> 💊 现在该吃 **PPI(雷贝拉唑)1 粒** —— **空腹/饭前 30 分钟**。还有 25 分钟可以吃早饭。
> [已吃] [跳过] [推迟 10 分钟]

`[已吃]` = 通知 action button 直接写 MedicationLog(无需进 App)。iOS category
`MEDICATION_REMINDER` 已存在；增加 action 属原生变更，当前只能进入 production 人工
原生 Gate，不能自动创建 production build。

**漏服智能补救(后果不对称)**:
- PPI 漏服 → "补吃即可,别和下一次叠"。
- 抗生素漏服 → "想起来就尽快补,但若快到下一次就跳过别加倍;漏多了告诉医生(影响根除率)" —— 走安全话术,不乱建议加量。

---

## 6. 安全集成(用户已 12 种药 + 长期 PPI,这是必经)

引入根除方案会**叠加多种新药**,必须过闸门:

1. **引入即校验(硬闸门)**: 实例化方案前,SafetyGuardian 跑全量 DDI/PGx/DSI(新药 × 已有 12 药)。
   - **克拉霉素是 CYP3A4 强抑制剂** → 若用户在吃他汀,现有 `ddi_statin_cyp3a4_inhibitor` 直接命中(HIGH);叠华法林/某些钙拮抗剂同理 → 阻断 + 提示就医。
2. **新增长期 PPI 规则**(`rules/ddi.py` 或新建): 用户**本就长期 PPI**,根除期再叠根除剂量 PPI → 提示长期 PPI 的 B12/镁/钙吸收、骨折、复发性 CDI、肾功能监测,以及"根除结束后是否继续长期 PPI 该与医生评估"。(Explore 实测:当前**无**任何长期 PPI 规则,是真空白。)
3. **PGx**: CYP2C19 影响 PPI 代谢与根除成功率;现有 pgx.py 已覆盖 CYP2C19,实例化时若有基因数据应纳入解读(不自动调量,只提示)。
4. **铋剂注意**: 与奶制品/某些药需间隔 → 用 `spacing_min` 字段表达,提醒里体现。

---

## 7. 数据流(端到端)

```
医生处方(线下)
    ↓ 用户:选模板 / 拍处方OCR / 手填
Mobile 用药页 (mobile/app/medications.tsx + 新"方案录入"屏)
    ↓ 核对剂量 → 确认"这是医生开的"
POST /api/v1/medication/regimens   ← 新端点
    ↓
[硬闸门] SafetyGuardian DDI/PGx/DSI(新药 × 已有12药)
    ├─ CRITICAL → 422 + 安全说明,不写入
    └─ pass ↓
medication_regimen_service.instantiate()
    ├─ 建 MedicationRegimen(phases)
    ├─ 建 N×Medication(带 timing_relation/meal_anchor)
    └─ medication_course_service → ReviewSchedule(PPI→胃镜)
    ↓
─────────── 每日运行 ───────────
Celery scan_medication_reminders(每分钟,已存在)
    + 饮食打卡事件(策略B)→ reminder_service.fire_reminder
    ↓ APNs(action: 已吃/跳过/推迟)
用户点"已吃" → POST /medication/logs → MedicationLog
    ↓
Twin medication 分区(active_meds + adherence + course_phase + days_left)
    ↓
DailyOperatingPlan.actions 注入当日用药条目(补 0% 缺口)
    ↓
到第15天:阶段机停3药、PPI改1次/日、推"进入愈合期"
    ↓
疗程结束:ReviewSchedule 触发"约胃镜/呼气复查"
```

---

## 8. 分期落地(反馈环优先)

| 阶段 | 内容 | 端 | 反馈环 |
|---|---|---|---|
| **P0 (MVP,1 周内可用)** | ① Medication 加 `timing_relation`/`meal_anchor` 字段 + 迁移 ② 提醒文案带"饭前/饭后/空腹"+ 完整剂量 ③ 通知一键"已吃"(iOS) | backend + mobile | 后端 pytest；Mobile 仅 Simulator 验证，物理 iOS 验收冻结；所有 OTA/native 发布 Gate 均 BLOCK |
| **P1 (方案 + 阶段)** | ④ MedicationRegimen 模型 + 模板引擎(Hp 四联/三联)⑤ 阶段自动切换 ⑥ 引入即 DDI 校验硬闸门 ⑦ 接 medication_course_service 复查 | backend 重 | 后端 pytest 为主 |
| **P2 (耦合饮食 + Daily Plan)** | ⑧ 相对吃饭智能提醒(学习型+事件型)⑨ 注入 DailyOperatingPlan ⑩ 长期 PPI 安全规则 | backend + mobile | 本地 Metro/Simulator 验证；发布 Gate BLOCK |
| **P3 (硬件,可选)** | L1 分装图生成;L2 BLE 药盒回写接口 | mobile | 按需 |

**先做 P0**:它独立交付价值(吃药当下不用再查"这个饭前还是饭后"),改动最小,反馈环最短,不依赖方案引擎。

---

## 9. 不做 / 留后续(防蔓延)
- ❌ 自动开方 / 调量 / 换药(永久不做,安全红线)
- ❌ 自研智能硬件
- ⏳ 家人代管用药、药房自动续方、医保对接、Android 全套通知 action

---

## 附录 A. 复用清单(Explore 2026-06-14 实测)
| 模块 | 文件 | 复用方式 |
|---|---|---|
| 药物模型 | `backend/app/models/medication.py` | 加字段 |
| 提醒扫描 | `backend/app/tasks/notifications.py:scan_medication_reminders` | 复用 |
| 提醒服务 | `backend/app/services/reminder_service.py` | 复用 |
| 依从日志 | `MedicationLog` | 复用 + 通知一键 |
| Twin 分区 | `backend/app/twin/schema.py:MedicationState` | 加 course_phase/days_left |
| 疗程→复查 | `backend/app/services/medication_course_service.py` | 复用(PPI→胃镜已映射) |
| 安全规则 | `backend/app/agents/safety_guardian/rules/{ddi,pgx,dsi}.py` | 复用 + 补长期 PPI |
| 一方 Agent skill | `backend/skills/medication-tracker/SKILL.md` | 复用(对话式录入) |
| 前端页 | `frontend/src/app/medication/page.tsx` | 加方案视图 |
| 移动端 | `mobile/app/medications.tsx`、`mobile/services/medicationReminders.ts` | 加方案录入屏;Android 通知待补 |
| 通知 | `backend/app/services/notification/push_service.py` | 复用 |

> 已实测**确缺**:① Medication 无 `timing_relation` ② 无 MedicationRegimen/疗程阶段 ③ DailyOperatingPlan 0% 用药集成 ④ 无任何长期 PPI 安全规则。本设计四处新建即对应这四个真空白。
