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
距离 **"AI 健康操盘手"** 还差 3 件结构性事：

1. **主动循环管理** (Open-Loop Manager)
2. **临床记忆** (Clinical Journal / Case Timeline)
3. **外部指令通道** (External directive channel — 用户/家人/教练 而非医生)

这 3 件做完，就是国内独此一家的产品。
**不缺技术。缺的是克制 + 把现有的东西串起来的耐心。**

---

## 一、现状盘点（2026-04-28 数据）

### 代码体量
```
后端:   30,692 行 services + 5,796 行 models + 17,185 行 tests (81 测试文件)
        110 个 API router, 74 个 SQLAlchemy 模型
前端:   213 个 .tsx, 69 个顶级路由
移动:   90 个 .tsx, 5 个 Tab
Skills: 23 个 OpenClaw skill
```

### 4 层架构

```
L4 Orchestrator   → intent 路由 + specialist 编排 + 信任循环落地 + 自我学习反馈
L3 Specialists×10 → SafetyGuardian (51 规则) + 4 个生理 + 3 个慢病 + 知识/纵向
L2 Digital Twin   → 13 语义分区 snapshot + Redis 5min 缓存
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

| # | 问题 | 解决路径 |
|---|---|---|
| A | 数据可信度链条有断点 (Garmin sync 单点) | Twin 加 `data_source_confidence`, fallback 链 |
| B | "假装做了"的边界没守住 (LLM 工具参数幻觉) | `tool_call_validator` 中间件 |
| C | Twin 是"现在"不是"叙事" | clinical_journal + case_thread 表 |
| D | Specialist 之间是"并发独立"不是"讨论" | multi_agent_debate + LLM 仲裁 |
| E | 医生不在环 (商业天花板) | doctor email loop + reply parser |
| F | 复杂度欠账 (garmin_connect/notifications 等大文件) | 持续拆 |
| G | 运营盲区 (Sentry 未配置, caller=unknown 多) | 接 DSN, set_caller 补全 |

---

## 四、12 个月愿景

> **一个家庭医生级的 AI 健康操盘手 — 它知道你的基因、化验、可穿戴数据、用药史，每天主动跟进你的开放健康循环（labs 复查、计划进度、症状变化），每周把异常打包推给你的人类医生，医生指令反馈进来又驱动 AI 调整你的日常。**

### 7 个维度的从→到

| 维度 | 现状 | 12 月后 |
|---|---|---|
| 触发 | 用户问 → AI 答 | AI 主动 → 用户决定 |
| 记忆 | Twin snapshot + 对话片段 | Clinical Journal (SOAP) + Case Timeline |
| 裁决 | LLM 黑盒 + 51 规则 | Multi-Agent Debate + 医生指令注入 |
| 验证 | ActionCard outcome (✅ 已上) | 全部建议进信用循环 |
| 覆盖 | 个人 | 家庭 (老人/配偶/孩子) |
| 触达 | App / 推送 | App / 推送 / 真人医生周报 |
| 商业 | 个人工具 | Free + Pro + Concierge 三档 |

---

## 五、6 阶段 Roadmap

### **阶段 1 (0–4 周): 守门 + 观测**

P0 防黑天鹅，让线上不再有"AI 假装做了"的 silent failure。

- [x] ActionCard outcome tracking (2026-04-27)
- [x] specialist proposed_cards × 5 (2026-04-27)
- [x] orchestrator 自我学习注入 hit-rate (2026-04-27)
- [x] LLM 日期幻觉守门 (2026-04-27)
- [ ] **`tool_call_validator` 中间件** (3-5 天)
  - 数值范围、日期、引用 ID 存在性、用户授权范围统一守门
- [ ] **接 Sentry DSN** (前后端 2 个项目, 1h + 等审)
- [ ] **set_caller 补全** (LLM caller 从 unknown → < 20%, 1 天)

### **阶段 2 (5–8 周): Open-Loop Manager**

核心 agent 感。

- [ ] 每日 7am Celery 扫所有"开放循环"
  - 过期 lab 复查
  - 到期 ActionCard
  - Plan item 偏离
  - 异常趋势刚出现
- [ ] 评分排序，每天最多 2 条 APNs
- [ ] User feedback：可"打分/不感兴趣/暂停 X 天"

成果：**用户从"我去问 AI" 变成"AI 在管我"**。

### **阶段 3 (9–14 周): Clinical Journal**

- [ ] `clinical_journal_entries` 表 (SOAP 结构)
- [ ] `case_threads` 表 (按主题/疾病聚合)
- [ ] 每次对话/简报后 LLM 自动产 SOAP entry (旁路)
- [ ] Specialist prompt 优先注入相关 case timeline
- [ ] 前端 case timeline UI

成果：**AI 真的"记得你"**。

### **阶段 4 (15–22 周): Multi-Agent Debate + Doctor-in-the-loop**

- [ ] Specialist cross-review (FuelStrategist 看 MetabolicSpecialist 发现, 矛盾 escalate)
- [ ] LLM 仲裁层 (两 specialist 矛盾时必须明示)
- [ ] Doctor email weekly report v1
- [ ] Doctor reply parser → user_directives → specialist 遵循
- [ ] Concierge tier 雏形 (内测一个真人医生 24h 内回复)

成果：**从工具升级到服务**。这是真正的付费理由。

### **阶段 5 (23–34 周): Household Twin**

- [ ] household_twin 模型 (每成员 sub-twin, 跨人推理)
- [ ] 多人 ActionCard 分配机制
- [ ] 隐私分区配置

成果：**商业差异化最大化**。市场真空地带。

### **阶段 6 (35–52 周): Personal Knowledge Graph + Reasoning Trace**

- [ ] 个人知识库 (体检 OCR + 医嘱 + 过敏 + 历史成功干预) 进 ChromaDB user_partition
- [ ] Specialist 检索优先
- [ ] Reasoning trace: 每建议 trace 到 (data + rule/specialist + evidence + confidence)
- [ ] 用户可挑战 → 自动回放推理

成果：**B 端可卖**。可解释性是保险/医院/慢病管理的硬门槛。

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

## 七、当前优先级 (2026-04-29 更新)

**已完成（2026-04-29 一夜 ship 20 个 commit）**:

| # | 项 | 结果 |
|---|---|---|
| 1 | ~~tool_call_validator 中间件~~ | ✅ 6 个工具 + bypass-safe, 1e40478 |
| 2 | ~~set_caller 补全~~ | ✅ caller unknown 从 >20% → <20%, 571e372 |
| 3 | ~~Open-Loop Manager v1~~ | ✅ plan_deviation + mobile 反馈链路, 4c93aeb |
| 4 | ~~Clinical Journal v1~~ | ✅ briefing SOAP + specialist context, 17c54f7 |
| 5 | ~~Doctor Weekly Report v1~~ | ✅ Telegram 版激活（email 留 v2）, ce741f0 |
| 6 | ~~弱点 A 数据可信度链~~ | ✅ Twin 新鲜度标签, 737e0a1 |

**下一步优先级 (2026-04-29 重估)**:

| # | 项 | 工时 | 价值 | 状态 |
|---|---|---|---|---|
| 1 | **观察期** (首周真实数据) | 1 周 | ★★★★★ | 进行中 |
| 2 | **Sentry/GlitchTip 观测** | 1-2h | ★★★★★ | 未启动 (卡在选型) |
| 3 | 拆 `garmin_connect.py` (2800 行) | 1 天 | ★★ | 未启动 |
| 4 | 拆 `notifications.py` (1500+ 行) | 半天 | ★★ | 未启动 |
| 5 | Web 端 UX 一致性审计 | 1 天 | ★★ | 未启动 |
| 6 | Exercise 升级到 workout 完整模型 | 1 天 | ★★ | 未启动 |
| 7 | Apple HealthKit 集成 | 2 天 | ★★★ | 未启动 |

**不能跳过的原则**: 首周真实数据跑完之前不新增大 feature. 弱点 B (tool_call 幻觉)
弱点 C (Twin 叙事) 弱点 E (medic in loop) 均已打基线, 让时间验证.

---

## 修订日志

- 2026-04-28: 首版.
- 2026-04-29: 阶段 1-4 全部 v1 ship. STRATEGY 加弱点 A 数据可信度链 v1.
  Doctor report 从 email 退化到 Telegram (email 留 v2 等执业医师合作).
  优先级第 7 项重排: 观察期 + Sentry + 大文件拆分优先于阶段 5-6.
