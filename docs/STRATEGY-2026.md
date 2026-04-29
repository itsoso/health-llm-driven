# 健康 Agent 战略 — 2026

> **2026-04-28 写就**。此文档是项目方向的锚点，所有方向决策应回来对照。
> 修订需在 commit message 注明 reason，避免漂移。
>
> **合规边界**：本系统不提供医疗服务、不出具医嘱、不替代医生诊断。
> AI agent 的角色是**数据聚合 + 趋势分析 + 用户授权的硬性约束执行**。
> 任何涉及用药调整、治疗决策的内容必须由用户与其执业医师确认后再录入。

---

## 一句话定位

这套系统现在是 **"已经跑起来的 vertical health 多 agent 系统"**，不是 demo 也不是 PoC。

### 演进路径 (2026-04-30 确认)

```
个人 ──→ 家庭 ──→ 朋友圈 ──→ 更多人 (B 端)
```

- **个人** (现在): 产品 owner 自己每天在用；首要目标是**把自己的健康管理好**
- **家庭**: 父亲 / 配偶 / 孩子 的 sub-twin；家庭内数据共享 + 分级告警
- **朋友圈**: TestFlight Public Link / 微信小程序 的低门槛触达
- **B 端**: 保险 / 医院 / 慢病管理 / 健康险增值服务 — 可解释性 + 确定性规则是门票

**技术路线服务于演进路径**：每个阶段都不是另起炉灶，家庭复用个人的 Twin + KG + Safety，B 端复用其上的 Reasoning Trace 和审计日志。

距离 **"AI 健康操盘手"** 还差 3 件结构性事：

1. **主动循环管理** (Open-Loop Manager) — ✅ v1 已 ship
2. **临床记忆** (Clinical Journal / Case Timeline + KG) — ✅ 后端齐, UI 差
3. **外部指令通道** (执业医师 / 家人 / 教练) — ⚠️ Telegram 版 v1，真 concierge 闭环未启

**不缺技术。缺的是克制 + 把现有的东西串起来的耐心。**

---

## 一、现状盘点（2026-04-30 数据）

### 代码体量
```
后端:   47,338 行 services + 5,463 行 models + 19,710 行 tests (92 测试文件)
        108 个 API router, 65 个 SQLAlchemy 模型
前端:   213 个 .tsx, 69 个顶级路由
移动:   90 个 .tsx, 5 个 Tab
Skills: 22 个 OpenClaw skill
记忆:   4 层 (working/episodic/semantic/procedural) + 10 entity 类型 + 16 relation predicate
```

### 5 层架构 (原 4 层 + 新增记忆层, 2026-04-28)

```
L5 Memory/KG      → 事实级记忆 (MemoryFact) + 知识图谱 (Entity+Relation) + Hybrid Search
L4 Orchestrator   → intent 路由 + specialist 编排 + 信任循环 + 自我学习 + cross-review
L3 Specialists×10 → SafetyGuardian (51 规则) + 4 个生理 + 3 个慢病 + 知识/纵向
L2 Digital Twin   → 13 语义分区 snapshot + Redis 5min 缓存 + 数据新鲜度标签
L1 Collectors     → Garmin/Withings/CGM/化验PDF/基因/环境/补剂/用药...
```

### 信任循环（2026-04-28 上线）

```
specialist.run() → proposed_cards → ActionCard 落地
       ↓ N 天后
outcome_grader 自动评分 (0-100)
       ↓
specialist hit-rate 注入下次 LLM prompt
       ↓
越用越准
```

### 记忆层 (Sprint 5, 2026-04-28 提前 ship)

原 STRATEGY 阶段 6 的 Personal KG 基础设施已经就绪。具体范围:

- **MemoryFact** (三元组 subject/predicate/object): 事实级可衰减记忆, 4 层寿命分级
- **HealthEntity** (10 类型 × aliases × attributes): medication / symptom / lab_value / vital / condition / intervention / lifestyle_factor / gene_variant / supplement / anatomical_target
- **EntityRelation** (16 种 typed predicate): treats / causes / triggers / interacts_with / contraindicates / responds_to / ...
- **Hybrid Search**: BM25 (中文 2/3-gram) + Graph 2-hop + RRF 融合
- **Decay + Crystallization**: Celery 04:00 跑; working → episodic → semantic 自动升级
- **Ontology 文档**: `docs/HEALTH_AGENT_ONTOLOGY.md` 描述 ingest / 矛盾解决 / 隐私规则

**意义**: 阶段 6 "Reasoning Trace + B 端可解释性"的基础已经免费拿到, 只差 trace UI 这一层.

---

## 二、真正的护城河（差异化）

### ① 51 条确定性安全规则 + Twin 13 分区聚合
- 市面 90% health AI 是 "大模型 + 提示词"。
- 你是 **deterministic engine + LLM-on-top**：DDI 药物相互作用 / DSI 补剂 / PGx 基因药物 / vitals / labs / training_load / CGM 共 7 类 51 条
- LLM 只做"翻译"，不做"判断"

### ② 基因 × 数据 × 干预的三角闭环
- MTHFR/APOE/FTO 影响营养建议
- CYP2D6/CYP2C19/SLCO1B1/G6PD/HLA-B*5701/DPYD/ALDH2 影响用药安全
- 国内做基因检测的不少，**把基因接入日常对话+安全告警**的极少

### ③ 多源数据 + 长期视角
- LongitudinalAnalyst 6 月趋势 + 干预×指标因果叙事
- ActionCard outcome tracking 把分析升级成行为信用

### ④ 多端 + 实时通知
- Web + iOS RN + 微信小程序 + APNs + EAS Update OTA
- chat-driven action loop，不是单纯 chat

---

## 三、真正的弱点（结构性）

| # | 问题 | 解决路径 | 状态 (2026-04-30) |
|---|---|---|---|
| A | 数据可信度链条有断点 (Garmin sync 单点) | Twin 加 `data_source_confidence`, fallback 链 | ✅ 新鲜度标签 v1 ship (737e0a1) |
| B | "假装做了"的边界没守住 (LLM 工具参数幻觉) | `tool_call_validator` 中间件 | ✅ 6 工具 + bypass-safe (1e40478) |
| C | Twin 是"现在"不是"叙事" | clinical_journal + case_thread 表 + KG fact | ✅ Journal + Sprint 5 KG / ⚠️ 前端 UI 差 |
| D | Specialist 之间是"并发独立"不是"讨论" | cross_review + LLM 仲裁 | ⚠️ cross_review 规则层 ✅ / LLM 仲裁 ❌ |
| E | 医生不在环 (商业天花板) | doctor email loop + reply parser + concierge | ⚠️ Telegram 版 + webhook 回复 / 真医师合作 ❌ |
| F | 复杂度欠账 (garmin_connect/notifications 等大文件) | 持续拆 | ❌ garmin_connect 2800 / notifications 1500+ |
| G | 运营盲区 (Sentry 未配置, caller=unknown 多) | 接 DSN, set_caller 补全, 观察期看板 | ⚠️ set_caller ✅ / Sentry ❌ / 看板 🚧 |

---

## 四、12 个月愿景

> **一个家庭医生级的 AI 健康操盘手 — 它知道你的基因、化验、可穿戴数据、用药史，每天主动跟进你的开放健康循环（labs 复查、计划进度、症状变化），每周把异常打包推给你的人类医生，医生指令反馈进来又驱动 AI 调整你的日常。**

### 7 个维度的从→到

| 维度 | 现状 (2026-04-30) | 12 月后 |
|---|---|---|
| 触发 | ✅ AI 主动 → 用户决定 (Open-Loop v1) | 反馈学习闭环 v2 |
| 记忆 | ✅ Twin + Journal + 🚀 Sprint 5 KG | Reasoning Trace 可回放 |
| 裁决 | ⚠️ LLM + 51 规则 + cross_review 规则层 | Multi-Agent Debate + 医生指令注入 |
| 验证 | ✅ ActionCard outcome 信用循环 | 全部建议进信用循环 (包括 open-loop) |
| 覆盖 | 个人 (产品 owner 日用) | 家庭 (老人/配偶/孩子) → 朋友圈 |
| 触达 | ✅ App / APNs / Telegram 周报 | App / APNs / 真人医师 concierge |
| 商业 | ❌ 个人工具 (无付费) | Free + Pro + Concierge 三档 + B 端 |

---

## 五、6 阶段 Roadmap (2026-04-30 重排)

### **阶段 1 (0–4 周): 守门 + 观测** — ✅ 基本完成

- [x] ActionCard outcome tracking (2026-04-27)
- [x] specialist proposed_cards × 5 (2026-04-27)
- [x] orchestrator 自我学习注入 hit-rate (2026-04-27)
- [x] LLM 日期幻觉守门 (2026-04-27)
- [x] `tool_call_validator` 中间件 — 6 工具 + bypass-safe (2026-04-29, 1e40478)
- [x] `set_caller` 补全 (2026-04-29, 571e372)
- [ ] **接 Sentry / GlitchTip** — 卡在选型 (留到观察期后)
- [ ] **观察期数据看板** (2026-04-30 新增, 替代 Sentry 短期需求)

### **阶段 2 (5–8 周): Open-Loop Manager** — ✅ v1 ship

- [x] 每日 7am Celery 扫开放循环 (2026-04-29, 4c93aeb)
- [x] plan_deviation / 过期 lab / 异常趋势 3 类信号
- [x] 评分排序 + APNs 推送 + dedup
- [x] User feedback 回写 (done / snooze_7d / not_interested)
- [ ] **v2 反馈学习闭环** — dismissal rate 反调阈值 (等观察期数据)

### **阶段 3 (9–14 周): Clinical Journal** — ✅ 后端完成 / ⚠️ UI 差

- [x] `clinical_journal_entries` 表 (SOAP 结构)
- [x] `case_threads` 表 (按主题/疾病聚合)
- [x] 每次对话/简报后 LLM 自动产 SOAP entry (旁路)
- [x] Specialist prompt 优先注入相关 case timeline
- [ ] **前端 case timeline UI** — **最高优先级之一** (让"它记得你"对用户可见)

### **阶段 4 (15–22 周): Multi-Agent Debate + Doctor-in-the-loop** — ⚠️ 40% ship

- [x] Specialist cross-review 规则层 (2026-04-29, 9fdf896)
- [x] User directives 医生回复解析 (2026-04-29, f97e0ec)
- [x] Doctor weekly report v1 (Telegram 版, ce741f0)
- [ ] **LLM 仲裁层 v1** — 矛盾 specialist finding 才调 LLM (成本可控)
- [ ] **Concierge tier 雏形** — 签第一个人类医生 24h 回复
- [ ] Doctor email 版 v2 (等真实医师合作)

### **阶段 4.5 (23–28 周, 新增): 把阶段 4 做完 + 记忆展示**

STRATEGY 重排决定 — 阶段 5-6 之前必须先把阶段 4 的商业化和记忆 UI 补上.

- [ ] **Clinical Journal 前端 case timeline UI** (3-5 天) — 让 Sprint 5 的记忆层变可见
- [ ] **Reasoning Trace UI v1** (3 天) — 复用 Sprint 5 KG 几乎免费, trace 到 (data + rule + evidence)
- [ ] **LLM 仲裁层** (3 天) — specialist cross-review 遇矛盾时升级
- [ ] **Concierge 商业化包月** (1-2 天 + 商务合作)

### **阶段 5 (29–40 周): Household Twin** — 推迟, 等信号

- 原方案: household_twin 模型 + 多人 ActionCard + 隐私分区
- **触发条件**: 产品 owner 的父亲 / 配偶真的在用，且已有"别人也想用"的外部 pull
- **否则**: 不做. Household 是典型"想象中的需求", 没家庭用户信号不能预建

### **阶段 6 (41–52 周): 全面 Reasoning + B 端敲门砖** — 🚀 基础提前就绪

原方案: 个人 KG + Reasoning Trace. Sprint 5 已 ship KG 核心, 此阶段重定义:

- [x] Memory Facts 四层 + 10 类 entity + 16 predicate (2026-04-28, Sprint 5 A-E)
- [x] Hybrid Search (BM25 + Graph + RRF)
- [x] Decay + Crystallization cron
- [ ] **Reasoning Trace UI** — 由阶段 4.5 前置完成
- [ ] **B 端审计日志 API** — 给保险/医院的可查询接口
- [ ] **挑战-回放机制** — 用户对建议提异议 → 系统回放推理链
- [ ] **第一个 B 端客户** — 慢病管理 / 健康险增值 / 企业员工健康

---

## 六、**不要做**清单 (拒绝清单)

| ❌ | 原因 |
|---|---|
| 接更多 wearable (Whoop/Oura/华为高级权限) | Garmin+Withings+Apple Health 已 95%。再加 = 2x 维护，零差异化。 |
| AI 视频问诊 | 监管雷区 + 不是护城河 |
| AI 处方调整 | 法律红线 |
| 通用聊天 | 已有 ChatGPT/Pi |
| 多语言 | 国内单语高质量 > 多语低质 |
| 自研 LLM | 永远用最好的 OpenAI/Claude。差异化在数据+规则+闭环 |
| toC 大众市场 | 烧钱。先打 toC 高净值 |
| 所有 specialist 都套 LLM | 51 条确定性规则是护城河 |

---

## 七、当前优先级 (2026-04-30 重估)

**已完成（一夜 ship 20 个 commit + Sprint 5 五阶段）**:

| # | 项 | 结果 |
|---|---|---|
| 1 | ~~tool_call_validator 中间件~~ | ✅ 6 个工具 + bypass-safe, 1e40478 |
| 2 | ~~set_caller 补全~~ | ✅ caller unknown 从 >20% → <20%, 571e372 |
| 3 | ~~Open-Loop Manager v1~~ | ✅ plan_deviation + mobile 反馈链路, 4c93aeb |
| 4 | ~~Clinical Journal v1~~ | ✅ briefing SOAP + specialist context, 17c54f7 |
| 5 | ~~Doctor Weekly Report v1~~ | ✅ Telegram 版激活（email 留 v2）, ce741f0 |
| 6 | ~~弱点 A 数据可信度链~~ | ✅ Twin 新鲜度标签, 737e0a1 |
| 7 | ~~Sprint 5 A-E: Memory/KG 全套~~ | ✅ memory_facts + entities + relations + hybrid + decay + ontology (ac2bca6...e8b0281) |

**下一步优先级 (2026-04-30 演进路径 = 个人 → 家庭 → 朋友 → B 端)**:

| # | 项 | 工时 | 价值 | 阶段 | 为谁 |
|---|---|---|---|---|---|
| 1 | **观察期数据看板** (SQL + 打印) | 2h | ★★★★★ | 1 尾 | 个人: 让使用数据可见 |
| 2 | **观察期** (首周真实数据) | 1 周 | ★★★★★ | 1 尾 | 个人: 不新增大 feature |
| 3 | **Clinical Journal case timeline UI** | 3-5 天 | ★★★★★ | 4.5 | 个人: "它记得你" 对用户可见 |
| 4 | **Reasoning Trace UI v1** (复用 KG) | 3 天 | ★★★★ | 6 前置 | 个人 + B 端 素材 |
| 5 | **LLM 仲裁层** (矛盾才调) | 3 天 | ★★★ | 4.5 | 裁决质量 |
| 6 | **Concierge tier 商业化** (含真医师合作) | 1-2 天代码 + 商务 | ★★★★ | 4 尾 | 个人付费 + 商业化第一滴血 |
| 7 | 拆 `garmin_connect.py` / `notifications.py` | 1.5 天 | ★★ | 弱点 F | 工程债, 不急 |
| 8 | Sentry / GlitchTip | 1-2h | ★★★ | 1 尾 | 运营盲区 |
| 9 | Apple HealthKit | 2 天 | ★★ | 数据源 | Garmin 够用, 留后 |
| 10 | Household Twin | 1 周 | ★★ | 5 | 等真家庭用户信号 |

**不能跳过的原则**: 首周真实数据跑完之前不新增大 feature. 演进路径"先个人后家庭"要求当下所有动作都回答"这个是否让我 (产品 owner) 每天用得更爽".

**"个人先"的操作定义**:
1. 产品 owner 自己每天用 TestFlight App
2. 每周看观察期看板数据
3. 数据显示的痛点 = 这周要修的东西
4. 不为假想的"家庭用户"或"B 端客户"提前做功能

---

## 修订日志

- 2026-04-28: 首版.
- 2026-04-29: 阶段 1-4 全部 v1 ship. STRATEGY 加弱点 A 数据可信度链 v1.
  Doctor report 从 email 退化到 Telegram (email 留 v2 等执业医师合作).
  优先级第 7 项重排: 观察期 + Sentry + 大文件拆分优先于阶段 5-6.
- 2026-04-30: 演进路径明确 (个人 → 家庭 → 朋友 → B 端).
  补 Sprint 5 (Memory/KG/Ontology, 4 层记忆 + 10 entity × 16 predicate + Hybrid Search + Decay)
  到 §一 现状盘点 + §五 阶段 6 前置进度.
  新增 §五 阶段 4.5 补阶段 4 未完 + 记忆展示 UI, 推迟 Household Twin 到 5 阶段触发信号.
  §七 优先级按演进路径重排: Clinical Journal UI + Reasoning Trace + LLM 仲裁 + Concierge.
