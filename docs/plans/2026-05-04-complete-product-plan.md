# 完整产品规划 — Agent Native AI 健康操盘手 (2026-05-04)

> 取代 2026-05-02-next-season-roadmap.md 作为下一季优先级锚点.
> 输入: (1) 生产数据真实审计 (2) 2026 AI 健康赛道市场调研 (3) STRATEGY-2026 演进路径.

---

## 0. TL;DR

1. **现状**: 1 真实用户, **outcome_grader 评了 0 张**, **Open-Loop 投递失败 67%**, **Memory 注入 0 次被 Orchestrator 引用** — Agent Native 是名字不是事实.
2. **窗口**: FDA 2026-01 给 deterministic CDS 松绑 + Apple Health+ 2026 mid 是 24 月护城河时钟. **multi-agent + deterministic engine + KG 在消费级是空白**.
3. **12 周必做**: 关闭已有闭环 (Phase 0, 2 周) → 让 trust 对用户可见 (Phase 1, 4 周) → 撬动第 2-10 个用户 (Phase 2, 6 周). 不加新 specialist, 不加新数据源.
4. **12 月愿景**: 个人 → 家庭代理 → 朋友圈 (10-50 TestFlight) → B 端首单. 商业化第一滴血来自 Concierge (¥299/月, 真医师 24h 回复).
5. **不做**: Apple HealthKit / Android / 自研 LLM / 通用聊天扩展 / 多语言 / Kubernetes / 自媒体. 全部资源压在 51 规则 + KG + Trust Loop + 家庭代理.

---

## 1. 真实数据审计 (2026-05-04)

| 维度 | 现状 | 评估 |
|---|---|---|
| 真实活跃用户 (7d ≥3 操作) | **1** (itsoso) | 1 用户产品 |
| ActionCard 总数 / outcome 评过 | 13 / **0** | 🔴 信任循环没运转 |
| Open-Loop 推送投递成功率 | **33%** (4/12) | 🔴 67% 投递失败 |
| Memory facts 写入 / 引用 | 167 写 / **0 引用** | 🔴 写盲信 |
| client_events 事件种类 (7d) | **1** (journal_timeline_entered) | 🔴 埋点几乎空 |
| Garmin 7d 时序天数 | 8/8 | ✅ 采集稳 |
| 夜间 SpO2 7d samples | 3700 | ✅ 采集稳 |
| 基因 variants | 709 | ✅ 资产 |
| systemd / celery / LLM | 全活, $0.0052/7d | ✅ 基础设施稳 |

**结论**: 采集 + 基础设施 = 真资产. **Agent 闭环反馈侧 = 全盘空白.** Phase 0 必须修.

---

## 2. 市场窗口 (2026 调研要点)

- **监管绿灯**: FDA 2026-01-06 修订 CDS + Wellness 指南, 单一推荐 + 可独立 review 推理依据 → 免监管. 正面对齐 deterministic + reasoning trace 路线.
- **24 月时钟**: Apple Health+ (Mulberry) 2026 mid 上线, AI doctor + ChatGPT 整合; Garmin Chat Connector (MCP) 2026 春已 ship — wearable 数据锁定护城河塌.
- **学术验证你的架构**: Mount Sinai 2026-03 论文, multi-agent orchestrator 在 80 任务并发下胜出单 agent (16% / 65× compute). Nature npj 2025 论文 LLM 临床幻觉率 50-82% — deterministic 验证层是主流防线.
- **行业留存崩盘**: AI app 年留存 21% (RevenueCat 2026-03). Forward Health 2024-11 倒闭烧 $657M = 纯 AI 无医生模式被市场证伪.
- **消费级空白**: KG + RAG / Trust Loop / iOS Live Activity 在健康 app 都没大规模商用案例.

### 三层护城河 (按厚度排序)

| 层 | 内容 | 时长 |
|---|---|---|
| **L1 最厚** | 51 规则 + KG + Trust Loop 三件套 (修好后) | 长期持有 |
| **L2 中厚** | Twin 13 分区 + 家庭代理 (子女替父亲) | 12 月窗口 |
| **L3 薄** | 微信小程序 + 中医补剂 + 中老年用药 | 6 月战术加速 |

---

## 3. 12 个月四阶段

### Phase 0 — 关闭闭环 (Now → +2 周, 截止 05-18)

**核心命题**: 不加新功能, 让上一季 ship 的 Agent Native 闭环真的跑起来.

| # | 项 | 工时 | 验收 |
|---|---|---|---|
| 0.1 | outcome_grader 真评分 | 1.5d | 7d 内累计 ≥ 5 张 graded |
| 0.2 | Open-Loop 投递失败率 67% → < 10% | 2d | 7d 投递成功 ≥ 90%, ≥ 1 user_action |
| 0.3 | Memory 注入路径真被读 | 1.5d | 7d ≥ 30% orchestrator 输出有 memory 引用 |
| 0.4 | client_events 补 5 种事件 | 1d | 7d ≥ 5 种事件有数据 |
| 0.5 | Sentry DSN + Garmin 健康看板 | 1d | 看板正常, ≥ 1 错误捕获 |

**总工时**: 6 天. **不允许并发新 feature**.

### Phase 1 — Trust 对用户可见 (+2 → +8 周, 截止 06-29)

| # | 项 | 价值 |
|---|---|---|
| 1.1 | Agent 工作台 Tab (聚合 audit_log + action_card + alerts) | 把后台勤奋翻译成用户存在感, 直击 21% 留存问题 |
| 1.2 | ActionCard 执行能力扩展 (calendar / goal change / doctor question / concierge) | 突破"提醒 → 让用户去做" 的中间层 |
| 1.3 | Specialist 押注详情页 v2 (in-flight + graded history + scorecard) | 让 trust loop 具象化 |
| 1.4 | Forecast 推到全部 5 个生理 specialist | 当前只 2/5 押注, 数据稀疏 |
| 1.5 | Concierge 真医师商务接入 (代码 1-2d + 商务 ≥ 2 周) | 留存 21% 软肋的根治方案 |
| 1.6 | Open-Loop v2 反馈学习 (dismissal 反调阈值) | 推得少 + 准 |

### Phase 2 — 撬动第 2-10 个用户 (+8 → +20 周, 截止 09-21)

| # | 项 | 工时 |
|---|---|---|
| 2.1 | 家庭代理 v1 (子女替父亲) | 4 周 |
| 2.2 | PGx × 用药精准告警 v2 (user-specific cross) | 2 周 |
| 2.3 | 微信小程序 Twin 视图 (中老年触达) | 2 周 |
| 2.4 | 朋友圈 TestFlight 招募 ≥ 10 人 | 2 周 |
| 2.5 | B 端可解释性 API 雏形 (audit/trace endpoint) | 1 周 |

### Phase 3 — B 端入场券 (+20 → +52 周)

- B 端首单 (慢病 / 保险 / 健康险增值)
- npj Digital Medicine case study 投稿 ("Trust Loop in Production")
- 鸿蒙端评估 (触发条件: 华为 1000 万 watch 用户 + iOS 政策风险)

---

## 4. 北极星指标

| 时间窗 | 指标 | 目标 | 现状 |
|---|---|---|---|
| **Phase 0 / 2 周** | outcome_grader 累计评分 | ≥ 5 | 0 |
| | Open-Loop 投递成功率 | ≥ 90% | 33% |
| | Memory 引用率 (orch run) | ≥ 30% | 0% |
| | client_events 种类 | ≥ 5 | 1 |
| | Sentry 接入 + ≥ 1 错误捕获 | ✅ | ❌ |
| **Phase 1 / 8 周** | 周活跃天数 | ≥ 6/7 | — |
| | Agent 工作台周打开 | ≥ 10 | — |
| | Trust loop hit rate | ≥ 60% | — |
| | Concierge 签医师 | ≥ 1 | — |
| **Phase 2 / 20 周** | 真实活跃用户 | ≥ 10 | 1 |
| | 家庭代理双账号对 | ≥ 3 | 0 |
| | Concierge 付费用户 | ≥ 3 | 0 |

---

## 5. 不做清单

| ❌ | 原因 |
|---|---|
| Apple HealthKit | Garmin+Withings 已 95%, Apple Health+ 上线后他们做更好 |
| Android | iOS 立住前不做 |
| AI 视频问诊 / AI 处方 | 监管雷区 + 法律红线 |
| 通用聊天扩展 | ChatGPT 已存在, 差异化在 Twin+基因+化验 |
| 自研 LLM / 多语言 / Rust 重写 / K8s | 错配资源 |
| 自媒体引流 | 留存 21% 时拉新无意义 |
| 加新 specialist (第 11+) | 10 个够多, 深化现有 forecast/action |
| 等"观察期数据"再决定 | 5-04 教训: 没反馈是因没闭环, 不是没观察够 |

---

## 6. 风险

| # | 风险 | 对策 |
|---|---|---|
| R1 | Apple Health+ 提前进中国 | L1 护城河必须 Phase 0/1 内修好 |
| R2 | Phase 0 修不好 | 时间窗 2 周, 修不好就停 Phase 1 持续修. 可以接受慢, 不能接受绕过 |
| R3 | PGx 精准告警误报伤信任 | 每条 cross 规则人工 review + 分批 ship + 用户能反馈 "不准" |
| R4 | Concierge 医师签不到 | 备案: 接 丁香园/春雨/微医 marketplace API |
| R5 | 留存 21% 拍到自己头上 | Phase 1 Agent 工作台 + Trust 押注详情直接攻击 |
| R6 | 产品 owner 自己失去耐心 | Phase 0 直击此点, 关闭闭环让自己每天看到价值 |

---

## 7. 立即下一步 (本周 10 天)

不并发, 按顺序:

- **Day 1-3**: Phase 0.1 outcome_grader (含从对话固化卡的字段抽取)
- **Day 4**: Phase 0.2 Open-Loop 投递修复
- **Day 5-6**: Phase 0.3 Memory 注入路径
- **Day 7-8**: Phase 0.4 client_events + Phase 0.5 Sentry
- **Day 9-10**: 跑 7 天真实数据, 对照 §4 短期指标, 不达标继续修

**做完才进 Phase 1**.

---

## 修订日志

- **2026-05-04**: 首版. 取代 05-02-next-season-roadmap.md.
- **关键认知**: 上一份假设"观察期会自然反馈", 但 5-04 审计显示没反馈是因为闭环根本没在闭. Phase 0 = 修这个.
