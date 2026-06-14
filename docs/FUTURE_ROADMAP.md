# Future Roadmap — health-llm-driven

**盘点日**: 2026-05-06
**背景**: 14 天 276 commit 快速迭代后首次系统性盘点。产品能用,但内部复杂度在累积。这份文档是**方向性决策**,不是 todo list — 每项 trade-off 讨论到位,让 Owner 选,不是让 Claude 替 Owner 选。

---

## TL;DR (三句话决策)

1. **Garmin 数据利用率只有 30%** — 每天在浪费 API/DB/token 成本。可以选"砍采集"或"补消费",但不能两头挂着。
2. **Web 还是完整 App、Mobile 大量独占页** — 当前半承诺状态是最贵的。要么砍 web 到 admin-only,要么认真补 mobile parity。
3. **Specialist 层几乎无单测** — 这是真 Agent-Native 产品的死角,下次 prompt 改动可能悄悄回归,没人发现。

以上每一条都有不做的代价,但不做的代价**现在**还不痛,**三个月后**会。

---

## 决策记录 — 2026-06-11 (Owner 拍板)

经一次完整 code review(agent 核心 solid,风险全在"广度":4 端 + 137 router 增长快过收敛)+ 战略文档综合后,Owner 就本路线图悬而未决的三个方向性选择题拍板:

### D1. 产品形态 → ✅ 已决:抗衰 OS + 家庭/医生视图(= §3.1 选项 2)
- **北极星**:生物年龄闭环("证明你在变年轻")。代谢是入口钩子、抗衰是头条叙事;**验证闭环**(episodes + personal_outcome + longitudinal 因果)是真护城河 —— 检测谁都能做,"用你自己的数据证明某干预对你有效"做不到。
- **端定位**:mobile = 个人日常驱动;**Web 重定位为家庭/医生管理视图**(多人 + 权限 + 医生签字),不再追 mobile parity。与 Phase 2 家庭邀请 / 医生反馈一致。
- **级联**:User model 加家庭关系 + 权限层(往 (2) 走的代码量,前端架构剧变小)。

### D2. 客户端策略 → ✅ 已决:保留 4 端(mobile / web / mac / wechat)继续维护
- Owner 选择维持四端覆盖,**不砍 Mac**。
- **接受的代价 + 必须的遏制**(本决定的前提,进 TaskCreate 跟踪):
  - 每次后端 schema 改动要对齐 4 套类型 → **强制走生成类型护栏**(`mobile/types/api.generated.ts` + frontend 镜像 + Mac Codable 跨端核对;近因:`DeviceComparison.agreement` String→Double 解码 bug 就是这税)。
  - Mac 两个巨石文件(`HealthAgentMacApp.swift` ~5391 行 / `FeatureViews.swift` ~4282 行)**冻结增长 + 逐步拆**,新功能不许继续堆(近因:本周 RecordHubView ViewThatFits + NSViewRepresentable sizeThatFits 指数级布局卡死、markdown 每帧重解析卡顿,均已修)。
  - wechat 若长期无活跃用户,单独复审是否降级(不在本决定内)。

### D3. 多租户 / 商业化 → ✅ 已决:暂缓,先跑出抗衰闭环数据(= §3.3 推迟)
- 先用 MVP / Phase 2 攒真实 N-of-1 outcome 数据(融资 / 退出弹药)。
- 数据层**已 multi-user-ready**(merge 全程 `(user_id, record_date)` 为键,无 `user_id=1` 生产硬编码)—— 支付 / 配额 / 租户隔离审计等需求明确后再异步起架构。

### 由 D1–D3 顺带对齐(非新决定)
- **盲点 2(Web/Mobile 双轨)**:按 D1 解 → Web = 家庭/医生视图,mobile = 日常驱动;双轨保留但定位分清。
- **盲点 1(Garmin 采而不用)**:方向 = **补消费不砍采集** —— Phase 2 W2 把 VO2max 作第 2 个生物年龄信号、`training_readiness` 接进 RecoveryCoach(零成本高证据;多源平台已就绪,三源 Watch/RingConn/Garmin 已可并存对比)。
- **盲点 3(specialist 无单测)**:Phase 2 **前置必做** path A 最小单测(12 specialist 各:空 twin 不崩 / 典型出 JSON / 极端降级)—— 主动化放量 + LongevitySpecialist 转 tool-calling 前的回归护栏。

> 后续 code-health 清债(分层泄漏 4 处 / 增量巨石文件 / router 数纳入 doc-drift 闸门 / 裸 except)见 code review,按性价比另行排期,不阻塞 D1–D3。

---

## 决策记录 — 2026-06-14:行为闭环优先 + 取舍尺子(细化 D1,非推翻)

**一句话尺子(以后每个"要不要做 X"先过这把)**:
> **它让中年人更健康,还是只是让产品更聪明?** 让更聪明的(更多分析维度 / dashboard / 预测模型 / 基因炫技)= 默认降权;让更健康的(让人真做 + 坚持 + 看到对自己有效)= 优先。

**判断依据(为什么这把尺子)**:
- 中年人健康的瓶颈是**依从/行为**,不是信息——他们大多已知道该做什么,做不持久。**分析 ≠ 结果。**
- 系统的**输入/分析层已一流且边际递减**(Twin / 多源 / 12 specialist / 安全规则);再加分析对结局贡献趋近零。
- 这与 D1 北极星**一致**:D1 的真护城河本就是**验证闭环**("用你自己的数据证明某干预对你有效"),不是检测/分析本身。本记录把它**操作化**。

**聚焦的杠杆(80% 收益)**:代谢(胰岛素敏感/内脏脂肪/血脂血糖)· 心肺(VO2max/Zone2)· **肌肉(防少肌症)** · 睡眠 · **抓沉默杀手 + 筛查**(血压/血脂/血糖失控、癌筛)。慢病(鼻炎/胃炎等)价值在"触发→调行为→看改善"的闭环,不在一次性解读。

**下一条主线 = Phase 1:N-of-1 结局闭环**(见 [design-personal-predictive-model.md](design-personal-predictive-model.md))。这是把 D1 护城河变现的核心,也是唯一能**长期维持动机**的机制(证明"对你本人有效" > 任何 streak/徽章)。
- **诚实排序**(intervention_cycle 现 0 周期):① **闭环机制先行** —— 让"开一个干预周期 → 极简追踪 → 把结局清楚讲给用户(personal_outcome 时间线)"顺滑、主动(Celery 晨报只说今天最重要那一件);② **再上贝叶斯效应估计器**(层级贝叶斯 + 人群先验收缩,需 ≥5 周期数据,数据攒够才有意义)。
- **Phase 0(个人基线/异常,#170 已落)** 是燃料:给主动提醒 + 闭环供"你 vs 你自己"的信号。

**别做清单(降权,除非过了上面那把尺子)**:更多 specialist/分析维度 · 更多 dashboard 卡片 · 个人预测模型堆叠 · 基因 sequence-model(Evo/NT,对消费级已知 SNP 是 category error,维持 curated KB + PGx 规则)· 功能广度铺到第 N 个页面 · 虚荣指标式 gamification(bio-age"证明变年轻"措辞同此风险:实质 > 虚荣)。

---

## 一、核心盲点 × 3 (最大 RoI)

### 盲点 1: Garmin 数据 "采而不用" 30% 利用率

**现象**:
- 采集层 `backend/app/services/data_collection/garmin_getters_mixin.py` 每天拉 6+ 类数据: `endurance_score`, `hill_score`, `race_predictions`, `hydration_data`, `training_readiness`, `training_status`, `respiration_data`, `max_metrics` 除了 vo2max 的部分
- Twin schema (`backend/app/twin/schema.py` 13 分区) **零引用**这些字段
- 8 个 Specialist 里 movement_coach / recovery_coach 最该用 `training_readiness.score` / `endurance_score`,但代码里用的是 HRV + sleep 组合自己算

**为什么是问题**: 每天消耗 Garmin API quota (Connect API 有限流)、落盘空间、后续如果上 CGM/运动员 tier 还会继续堆。产品角度用户永远看不到这些数据 — 纯隐性成本。

**三个路径**:

| 路径 | 成本 | 收益 | 风险 |
|---|---|---|---|
| **A. 删采集** — 把 6 类字段从 getters_mixin 移除,停止采 | 1 天 | 立省 Garmin quota + DB 空间,简化 twin_builder | 将来想用得重爬 |
| **B. 填消费** — 把 `training_readiness` 接进 recovery_coach, `endurance_score` 进 movement_coach, `hydration_data` 进 fuel_strategist | 3-5 天 | 把 recovery readiness 从"自造轮子"换成 Garmin 官方分,说服力更强 | prompt 要重调 |
| **C. 中立** — 保留采集,二级存但不 builder 加载;标注 `_speculative` 前缀 | 半天 | 未来要用直接拉,不增复杂度 | 维持"看起来有,其实没用" |

**我的建议**: **A + B 混搭** — 删 `hill_score` / `race_predictions` / `max_metrics 非 vo2max` (明确用不到的),补 `training_readiness.score` 进 recovery_coach (已经有等价自算,换成官方源即可)。`hydration_data` 看你喝水 feature 真实度决定。

---

### 盲点 2: Web (Next.js) vs Mobile (RN) 的双轨制

**现象**:
- Web 有 53 个独占 route (`activity-status, analysis, dashboard, digital-twin, knowledge, news, points, friends, trip, achievements, health-report` 等)
- Mobile 独占 28 个 (`briefing, voice-chat, voice-style, siri, trace, doctor-loop, timeline, ai-profile, memory, directives, specialist, notification-settings` — 全是 14 天内新产物)
- **CLAUDE.md 写着 "mobile first"**,但实际 Web 在 prod 还活着且有完整 User flow
- 14 天 276 commit 大部分 mobile-only,Web 悄悄变 legacy

**为什么是问题**: 每次加 feature 你要问自己 "web 要不要跟?"。不跟 → 用户在 web 上看到的功能越来越残缺。跟 → 投两倍工时。一个人的团队不能两边都撑。

**三个路径**:

| 路径 | 取舍 |
|---|---|
| **A. 砍 Web 到 admin + marketing** — 删 35+ 非核心页 (news/points/friends/trip/achievements/analysis),留 dashboard + 管理后台 + 登录/注册/化验 PDF 查看 | 用户强行走 iPhone App,登录/注册 / 忘记密码仍可在 web,但日常健康交互一律 mobile |
| **B. 明确 Web 只服务"非本人查看"场景** — 家人代管、医生 review — 这些场景 mobile 难做 (需要登录切换 / 权限分离),web 反而有优势 | 重新定位 web = 多人协作面板,mobile = 本人 daily driver |
| **C. 双轨维持** — 现状,但引入强约束:每个 PR 模板加 "Web parity: [已做 / N/A / Tracked: #xx]" | 多一道检查 |

**我的建议**: **B** — 把 Web 重新定位成 "家庭健康管理员 / 医生视图"。这跟 G Phase 2 家庭邀请 + 保健医生反馈 (Memory 里提过老总刚需是异常报警推送) 是一致的战略方向。Mobile 是个人设备,Web 是关系网视角。

---

### 盲点 3: Specialist 层单测覆盖 = 0

**现象**:
- 8 个 specialist 里只有 `safety_guardian` + `recovery_coach` (hrv_timeseries) 有单测
- **零覆盖**: movement_coach, fuel_strategist, mental_health_companion, longitudinal_analyst, knowledge_librarian, 3 个 chronic specialists (hypertension/metabolic/rhinitis)
- 这些是用户看到 AI 结论的最后一层,prompt 改动完全没回归保护

**为什么是问题**: 真 Agent-Native 产品的价值在 "AI 判断靠谱" — 没测试等于每次 tune prompt 都是盲飞,回归靠用户在真机上撞见。与 docs/HARNESS.md 里 "verification is the bottleneck" 的核心理念自相矛盾。

**三个路径**:

| 路径 | 成本 | 边际收益 |
|---|---|---|
| **A. 每个 specialist 一个 test_basic** — 覆盖 (a) empty twin 不崩 (b) typical case 输出结构化 JSON (c) extreme case 降级 | 每个 0.5 天,共 ~3 天 | 至少不悄悄坏掉 |
| **B. 加 golden test** — 每个 specialist 固定 3-5 个真实 Twin snapshot,断言输出文本稳定性 (或用 LLM-as-judge 做语义稳定性) | 1 周 | 能检测 prompt drift |
| **C. 上线真实用户后靠 telemetry 驱动** — `agent_audit_log` 里查 outcome miss 率,大于阈值报警 | 现有基础设施 3-5 天 | 生产反馈闭环 |

**我的建议**: **A (必做) + C (中期)**。B 太重,单人团队投资回报比低。

---

## 二、低争议体力活 (任何时候可顺手清)

这些都是**明确**要做但不紧急的,建议攒够 2-3 个凑成一个 PR:

1. **删 habits.py** — `backend/HABITS_MODULE_REMOVAL.md` 确认废弃但文件未删
2. **删孤立 Mobile 组件** (12 个 0-import): `CounterChip`, `EditScreenInfo`, `ScoreRing`, `VitalTile`, `dashboard/GreetingHeader`, `HealthScoreHero`, `MiniStatusBar`, `TrendMiniCharts`, `data-health/DataPromptCard`, `design-system/RingGauge`, `design-system/SkeletonPlaceholder`, `chat/InlineCards`
3. **清根目录 160+ .md 历史报告** → `docs/archive/2026-04/`, `docs/archive/2026-05/` 按月归档
4. **`.gitignore` review**: `health.db` / `frontend/out/` / `*.log` 不该 track
5. **Android 决策** — 目前只有两个样板 `.kt`。三选一: (a) 删 `mobile/android/`,update CLAUDE.md 声明 iOS-only;(b) 写一份 `ANDROID_STATUS.md` 说明"未排期,未来 6 个月不做";(c) 排一个为期 2 周的 MVP Android sprint
6. **根目录 3 个 `ai-assistant-v{2,3,4}-preview.jsx`** — 确认是 design spike 还是可删
7. **mobile 大文件拆分**: `workout-detail.tsx 741`, `ai-profile.tsx 547` — 下次碰到顺手拆 sub-component

---

## 三、中长期方向性选择题 (要人做决定,不是我做)

### 3.1 产品形态

- **单人健康管家** (当前) — 你一个人用, specialist 都围绕"你"调
- **家庭健康仲裁者** — 老总 + 保健医生模式,中心是关系网 (web admin + mobile client 模式)
- **健康数据经纪人** — 采集端 + 对第三方 (医生、保险、体检机构) 开放 API,做数据钱包

三个方向的代码侵入性不同:
- 往 (2) 走:User model 改家庭关系,权限层重写,但前端架构剧变小 (web 就派上用场)
- 往 (3) 走:后端要加 OAuth provider + scope + rate limit,大工程

**你现在走的是** (1) 偏 (2):Siri / voice-chat / timeline 都是单用户,但 family / doctor-loop 在往 (2) 靠。决定走哪个会让许多技术决策一致起来。

> ✅ **已决 (2026-06-11)**:选 (2) 家庭/医生视图 + 抗衰 OS 北极星。详见顶部 §决策记录 D1。

### 3.2 Agent 深度

当前 specialist 是"规则 + LLM 合成",下一步可以:
- **更深的 memory** — 当前 memory 4-stage 还是单次对话级,没有跨月 / 跨年记忆
- **specialist 之间协商** — 当前 orchestrator 是串行调度,不是 agent 之间多轮 debate
- **用户反馈闭环强化** — `outcome_grader` 已经在跑,但没有把 miss 率喂回 prompt tune

**我的观察**: 深度方向是独立的 L10+ 叙事,值得开一个文档详细展开。docs/HARNESS.md 是技术基础,但没写"下一年 Agent 往哪长"。

### 3.3 商业化

TokenPlan provider 刚进来 — 这是未来 SaaS 化或者给朋友/家人开账号的基础。但:
- 还没有 billing
- 没有多租户数据隔离审计
- 没有 usage quota enforcement (现在只是 token plan 切换)

决定:要不要为真实多用户做 → 影响 next 6 个月基础架构投入。

> ✅ **已决 (2026-06-11)**:暂缓 SaaS,先跑出抗衰闭环数据;数据层已 multi-user-ready,需求明确再异步起。详见顶部 §决策记录 D3。

---

## 四、本 roadmap 怎么用

- **每周五看一次**,勾掉做了的,增补新发现的
- **决策一经做出**,本文对应节点加 `✅ 已决:<选项>,因为 <为什么>,<日期>` — 未来回看不会忘为什么
- **每次 commit 前反问**:"这次改动是推 roadmap 哪一项,还是新开坑?" — 新开坑要明确进 roadmap

本文件**不**是 todo list,是决策参考。具体任务去 TaskCreate 管理。

---

## 五、相关战略 / 设计文档(2026-06-11 归档入库)

这批文档此前散在工作树未提交(source-of-truth 漂移风险),现随本次决策一并入库。北极星 / 分期 / 工程设计的细节看它们,本文件只记**决策**。

| 文档 | 层级 | 内容 |
|---|---|---|
| [strategy-longevity-os.md](strategy-longevity-os.md) | 定位 | 抗衰 OS 北极星 + 生物年龄 Delta 指标 + 竞品/资本叙事(= D1 的依据) |
| [strategy-midage-men-health.md](strategy-midage-men-health.md) | 定位 | 中年男性入口(代谢钩子);被 longevity-os 收编为入口非头条 |
| [rfc-agent-native-health-os.md](rfc-agent-native-health-os.md) | 技术路线 | Agent-Native 10 方向(eval=dir9 是 dir1/3 主动化前置) |
| [product-evolution-plan.md](product-evolution-plan.md) | 综述 | 产品演进总览 |
| [design-longevity-mvp.md](design-longevity-mvp.md) | 工程设计 | PhenoAge 闭环 MVP(7 项血检字段 + golden test + LongevitySpecialist) |
| [plan-longevity-phase2.md](plan-longevity-phase2.md) | 规划 | Phase 2 工作流(VO2max / 主动 Watcher / DNAm / 协议编排 / Eval 看板) |
| [plan-longevity-phase3.md](plan-longevity-phase3.md) | 规划 | Phase 3(队列证据 + 规模化 + 礼宾/变现;仅 P3-3/4 纯代码) |
| [design-longevity-phase2-hardware.md](design-longevity-phase2-hardware.md) | 设计 | 硬件门控(BD 驱动,纯代码优先时暂缓) |
| [plan-next-horizon.md](plan-next-horizon.md) / [plan-toward-goal-v2.md](plan-toward-goal-v2.md) / [plan-product-improvements.md](plan-product-improvements.md) | 规划 | 近期改进 / 阶段目标(含"无 UI 不加 specialist"等纪律) |
