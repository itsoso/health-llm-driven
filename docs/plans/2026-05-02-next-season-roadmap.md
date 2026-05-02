# 下一季 Roadmap — Agent Native × 用户价值优先

> **2026-05-02 写就**. 上一季 ship 了记忆/推理可见化 v1, 观察期开始. 这份文档**不按 STRATEGY 原阶段 4.5/5/6 排**, 改按 **"Agent Native 闭环是否完整" + "产品 owner 每天用到的痛感"** 双维度重排.
>
> **北极星**: 产品 owner 自己打开 App 那一刻, 是否感觉 "AI 真在替我操盘"? 还是"又一个 dashboard + 聊天框"?

---

## 一、Agent Native 闭环 6 环节 — 当前状态诊断

```
[1 触发] 主动 → [2 记忆] 调用 → [3 裁决] 多专家 → [4 验证] 信任循环 → [5 触达] 多通道 → [6 商业] 医生
```

| 环节 | 现状 | 用户层面是否可感知 | 最大隐忧 |
|---|---|---|---|
| **1 触发** | Open-Loop Manager v1 + Safety 告警 + Siri (今天) | ✅ 能感知 | dismissal rate 没反调阈值 |
| **2 记忆** | 4 层 Memory + KG + Hybrid Search 全 ship | ⚠️ **用户感知弱** | 注入主链路是否真 work? 可能沉默失败 |
| **3 裁决** | 51 规则 + Specialist + cross-review 规则层 | ✅ 能感知 (Reasoning trace 刚 ship) | LLM 仲裁层还是空 |
| **4 验证** | ActionCard outcome + hit-rate 注入 prompt | ⚠️ **用户感知弱** | 用户不知道"AI 上次的建议命中没" 除非点 chip |
| **5 触达** | APNs + Telegram + Web + RN | ✅ 能感知 | 崩溃不可见 (Sentry 空) |
| **6 商业** | Doctor Telegram 周报 | ❌ **无真医师** | Concierge 名存实亡 |

**结论**: 环节 2 记忆 + 环节 4 验证是"后端做了, 但用户感觉不到" 的重灾区. 环节 6 商业依赖商务. 环节 5 触达缺 ops 盲区.

---

## 二、对用户 (产品 owner) 最有用的 Top 15 项

按 Tier 分组. Tier = (用户价值 × Agent Native 完整性) / 工时.

### Tier 1 · 高 ROI, 闭环补丁 (每条 0.5-2 天)

| # | 项 | 工时 | 为什么对用户有用 | Agent Native 闭环作用 |
|---|---|---|---|---|
| **T1.1** | **Memory 注入路径诊断** | 1 天 | 如果 AI 真记得我上周说的鼻炎发作, 我对它信任感不一样 | 环节 2 从"后端 sit" → "用户感知到" |
| **T1.2** | **Reasoning Trace 覆盖扩到 Specialist / Open-Loop** | 2 天 | 今天只 Safety 卡有"为什么", 推送里和 specialist finding 里都没有 — 信任感建一半 | 环节 3/5 一致性 |
| **T1.3** | **数据可信度在 UI 显式** | 1 天 | "基于 3 小时前 HRV + 昨晚睡眠" vs "现在建议早睡"  — 后者像指令, 前者像顾问 | 环节 3 透明度 |
| **T1.4** | **Push deep link 统一到 /trace/safety_{id}** | 0.5 天 | 点推送 → 看理由 → 做 action, 少一步中断 | 环节 5 闭环 |
| **T1.5** | **Sentry 接入** | 1-2h | 崩溃肉眼看不到 = 观察期数据可能假绿 | 环节 5 ops 底线 |
| **T1.6** | **Garmin 同步健康度 admin block** | 0.5 天 | Garmin 挂了 = 整个分析挂, 当前发现路径是"用户自己重试" | 环节 5 ops |

**Tier 1 合计**: ~6 天, **全部是闭环补丁不是新功能**, 符合"首周不新增大 feature" 原则.

### Tier 2 · Agent Native 能力深化 (每条 2-3 天)

| # | 项 | 工时 | 为什么对用户有用 | 触发条件 |
|---|---|---|---|---|
| **T2.1** | **基因 × 药物精准告警 (user-specific)** | 2 天 | "你在服的 X 药 + 你的 CYP2D6 慢代谢, 留意剂量" 比笼统 "你有 PGx 变异" 有用 10 倍 | 当前笼统 PGx rule → 交叉具体化. 产品 owner 本身在服异丙托溴铵 (memory) |
| **T2.2** | **LLM 仲裁层 v1** (STRATEGY 4.5 剩余) | 3 天 | Specialist 矛盾时给裁决 + 置信度, 不是两边都甩给用户 | cross-review 规则层已 ship, 有矛盾数据可喂 |
| **T2.3** | **挑战-回放机制** | 2 天 | 用户点"我不同意", 系统回放推理链 → 学习材料 + 建立"AI 愿意被质疑" 信任 | 依赖 Reasoning trace (刚 ship) |
| **T2.4** | **Open-Loop v2 反馈学习闭环** | 2 天 | dismissal rate 反调阈值, 推得少+准 | 需要观察期 dismissal 数据累积 |

### Tier 3 · 主动召回 (Agent Native 不依赖 App 打开)

| # | 项 | 工时 | 为什么对用户有用 |
|---|---|---|---|
| **T3.1** | **Siri Shortcut v2 + iOS Widget** (iOS 17+ Interactive Widget) | 2-3 天 | 今日 readiness 直接主屏看, 不用开 App. 对 Agent Native "随时可用" 是关键 |
| **T3.2** | **Live Activity (跑步/睡眠期间)** | 3 天 | 跑步时实时心率带提醒, 睡眠时 SpO2 异常提醒, 灵动岛直出 |

**触发条件**: Siri v1 (今天刚 ship) 真用起来了再扩.

### Tier 4 · 商业化 (gated by 商务)

| # | 项 | 工时 | 前置 |
|---|---|---|---|
| **T4.1** | **Concierge 真医师合作** | 1-2 天代码 + 商务 | **商务**: 签第一个医师 (≥2 周). 代码侧先建付费层 / 医师账号等于空转 |
| **T4.2** | **Household Twin (给父亲装)** | 1 周 | 有家庭成员 pull. 产品 owner 父亲真的愿意用为触发 |

### Tier 5 · 工程债 (ROI 低, 但改一次爽)

| # | 项 | 工时 | 何时做 |
|---|---|---|---|
| **T5.1** | 拆 garmin_connect.py (2800 行) | 1.5 天 | 下次接 Withings/HealthKit 前做 |
| **T5.2** | 拆 notifications.py (1500 行) | 1 天 | 下次动推送逻辑时顺手 |
| **T5.3** | Mobile follow-up polish list (5 项) | 半天累计 | 下次碰对应文件顺手 |

---

## 三、推荐执行顺序

### **本周** (观察期, Day 1-7): 只做 Tier 1 中不新增 feature 的项

- **Day 1**: T1.5 Sentry 接入 (1-2h) + T1.6 Garmin 同步健康度 block (0.5 天)
- **Day 2-3**: T1.1 Memory 注入诊断 (1 天)
  - 若发现注入断了 → 立刻修 (可能 +1-2 天, 但这就是观察期数据该暴露的坑)
- **Day 4**: T1.4 Push deep link 统一 (0.5 天)
- **Day 5-7**: **停手**. 看看板数据 + 真机用. 记录意外.

**硬约束**: 本周不碰 Tier 2+. 原因是 §七 "首周真实数据跑完之前不新增大 feature". Tier 1 全部是"修上季坑"不是新 feature.

### **第 2 周** (基于观察期数据): Tier 1 剩余 + Tier 2 挑 1

- T1.2 Reasoning Trace 覆盖扩 (2 天) — 上周观察期里如果"为什么" 按钮被点了 ≥20% = 扩大投入
- T1.3 数据可信度 UI (1 天)
- **按数据决定 Tier 2 第一个**:
  - 若 memory 注入诊断发现真断了 → 不算 Tier 2, 继续修
  - 若 dismissal rate 高 → T2.4 Open-Loop 反馈学习
  - 若 specialist 矛盾数据有量 → T2.2 LLM 仲裁层
  - 若 Safety 推了但用户不做 action → T2.3 挑战-回放

### **第 3-4 周** (Tier 2 第二个 + 考虑 Tier 3)

- 完 Tier 2 第二项
- 若 Siri 数据证明用得上 → T3.1 Widget/Siri v2

### **中期 (1-2 个月)** 

- Tier 5 工程债按"碰到就拆"节奏
- Tier 4 等商务
- Tier 3 剩余按使用信号

---

## 四、**不做清单** (拒绝的诱惑)

| ❌ | 原因 |
|---|---|
| 接 Apple HealthKit | Garmin + Withings 已覆盖 95%, 加 HealthKit = 2x 维护, 零差异化 |
| 社交/分享功能 | "给朋友看我今天多少步" 不是健康操盘手该做的 |
| AI 视频问诊 | 监管雷区 |
| 通用聊天扩展 | 已有 ChatGPT. 差异化在"基于你的 Twin + 基因 + 化验" |
| Android OTA | Mobile 还没 Android build, 等 iOS 立住 |
| 自研 LLM | 用最好的 API, 差异化在数据+规则+闭环 |
| 后端 Rust 重写 | 当前 FastAPI 性能够, 重写 ROI < 0 |
| 上 Kubernetes | 单台 ECS 够撑, 不要复杂度给自己 |
| LangChain/LlamaIndex 换依赖 | 自己的 Orchestrator 已 work, 不引新依赖 |

---

## 五、硬指标 (观察期 + 下一季判断依据)

### 观察期 (本周) 的 go/no-go 信号

从 `/admin/observability/dashboard`:

| 信号 | 看法 |
|---|---|
| Reasoning 抽屉点击率 ≥20% | T1.2 Reasoning 覆盖扩放大投入 |
| Reasoning 抽屉点击率 <5% | 放弃 T1.2, 诊断是按钮不显眼还是内容没价值 |
| Journal tab 进入 ≥10 次 | case timeline 达预期 |
| Journal tab 进入 <3 次 | timeline 没用, 要么 UI 要么位置 |
| Specialist 详情页进入率 >0 | chip row 起效, 考虑 Widget 化 |
| Specialist 详情页零进入 | chip 不够显眼 或 scorecard 数据不够有趣 |
| Sentry 抓到崩溃 ≥1 次 | 立刻修 + 加回归测试 |
| Celery Health 出现 stale | 立刻修调度 |

### 下一季 (第 2-4 周) 的"做得好"判据

- [ ] 产品 owner 在 App 里主动点"为什么" ≥10 次/周
- [ ] 至少一次"看了 reasoning 觉得 AI 错了, 回头改规则/prompt"
- [ ] AI 对话至少一次引用了 case_thread / memory_fact (从后端 prompt log 可验证)
- [ ] Sentry 总错误数 < 5/周, 无连发同样错误
- [ ] Siri shortcut 被用 ≥2 次/周 (log_orchestrator_run source=siri 计数)
- [ ] 无数据鸿沟: 用户感到"AI 不知道我 Y" 但实际 Y 已在 Twin 里 = 0 次

---

## 六、风险清单

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 观察期数据显示 Reasoning 抽屉点击率 <5% | 上季 2 周白 ship | **可接受**. 数据驱动就是承担这种风险. 止损: T1.2 不做, Reasoning 功能保留 (至少 explain 能力存在) |
| R2 | Memory 注入诊断发现真断了 | T1.1 实际 3 天不是 1 天 | 这是观察期该暴露的, 优先级 0 必修 |
| R3 | 基因 × 药物精准告警误报 | 用户信任崩塌 | **极高风险**. 做前必须人工 review 每条交叉规则, 分批 ship, 不要一次开 50 条 |
| R4 | Siri v2 Widget 在非 iOS 17 设备上 crash | App Store 审核挂 | iOS 17+ gating, 降级不展示 |
| R5 | Open-Loop v2 阈值学习把 push 调到太少 | 用户错过重要告警 | severity=CRITICAL 永不被学习调低 |
| R6 | Sentry 捕获过多 PII | 合规 | 开启 Sentry PII 脱敏模式, 不传 message body |

---

## 七、修订日志

- **2026-05-02**: 首版. 记忆/推理可见化 v1 ship 当天. 以 Agent Native 闭环 + 产品 owner 视角重排. 核心观点: 先补闭环缺口 (Tier 1) 再加能力 (Tier 2), 本周只做 ops 类项 遵守"观察期不新增 feature".
