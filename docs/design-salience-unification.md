# 设计文档：统一 Salience 引擎（reactive chips × proactive push）

> 状态：**设计稿，待评审**。评审通过前不写实现代码。
> 实现必须在**独立 git worktree**里做（backend 共享 checkout 有并发 agent，分支会在 tool call 之间翻转 —— 见 `MEMORY.md / project_shared_worktree_use_git_worktree`）。

---

## 0. 一句话

把两套各自判断"用户此刻该被提醒什么"的逻辑（chip 的 23 个 `_suggest_*` / push 的 5 个 `_detect_*`），收敛到**一层中立的 `SalientSignal`（domain + severity + evidence + surfaces）**。检测/阈值/严重度逻辑共享一次；chips 和 push 各自从 `SalientSignal` **适配**出自己的输出类型和下游，保留各自的"声音"和投递语义。

---

## 1. 四问（feature-plan）

### Why — 解决什么问题
- **现状**：两套引擎都在判"什么最重要"，阈值/优先级逻辑**重复且会发散**。最典型：HRV 下降。
  - chip `_suggest_hrv_today`：`今天HRV vs 7日均值`，跌 15% → priority 90
  - push `_detect_trend_anomaly`：`近7天均值 vs 前7天均值`，跌 15% → score 60+
  - **同一个意图，两套数学，两个文案，改一边不会同步另一边。**
- 同类重叠还有：`sync_stale` ≈ `_suggest_recovery_history`（数据缺口）、`plan_drift` ≈ `_suggest_supplement`（依从率）、`lab_overdue` ≈ `_suggest_exam`（化验跟进）。
- **量化目标**：阈值/严重度逻辑**单一真相源**（DRY）；新增一个"该提醒"的判断只写一次，自动两端生效；chip CTR（`client_events`）与 push feedback（`open_loop_history`）共享 `(domain, signal_key)` 词表，可在 `observability_service` 把两条漏斗 join 起来回答"HRV-drop 这个信号，chip 还是 push 更被用户接受？"

### What NOT — 边界
- **不统一"声音/文案"**。chip 是**问句**（喂给对话框的 prompt），push 是**陈述句故事**（"为什么+做什么"）。共享的是 *evidence（数字）*，不是 *prose（文案）*。
- **不统一下游**。chip 无 dedup / 无 quiet-hours / 要随机变化；push 有 dedup + snooze + quiet-hours + APNs/Telegram + history 回调。这些**全部留在各自的 adapter**，不进共享层。
- **不动 APNs / Telegram / history schema / 反馈回调链路**。signal_key 字节级保持不变（dedup 连续性，见 §5 风险 1）。
- **不 big-bang**。一次迁移一个 detector，push 侧先 shadow 再 cutover。
- **本期不做**：chip 与 push 的统一调度器 / 跨端去重（"今早 push 过 HRV，下午 chip 就不再出 HRV"）—— 诱人但增加耦合，留到统一层稳定后单独评估。

### How — 最简路径
- 新增 `backend/app/salience/` 包：`SalientSignal` 数据类 + `SalienceContext`（复用现有 `_collect_signals`）+ `render_chip` + `render_push` 两个 adapter + `detectors/`。
- **第一刀切 HRV drop**（重叠最高、风险可控、正好是发散范例）：一个共享 `detect_hrv_drop(ctx)`，**一个阈值常量**。
- 数据流见 §2。反馈环：纯 backend `pytest`，秒级；push 侧 cutover 用 shadow-log 灰度（不靠真机）。

### What could go wrong — 见 §5 风险清单

---

## 2. ASCII 数据流

### 现状（两套并行）

```
用户开聊天                                  Celery cron 08:45（全用户）
    ↓                                            ↓
GET /agent/conversation-starters         run_open_loop_check
    ↓                                            ↓
compute_conversation_suggestion_cards    collect_open_loops
    ↓                                            ↓
_collect_signals → StarterSignals        5× _detect_*(db, user_id)
    ↓                                            ↓
23× _suggest_*(signals)                  → OpenLoop(kind,title,body,score,
    ↓  SuggestionCandidate(prio,text,key)         deeplink,signal_key,metadata)
_select_cards (critical+weighted random)      ↓ sort desc, top 2, score>=50
    ↓                                       _push_loop:
{text,key,priority} → chip UI                  settings gate → quiet-hours →
    ↓                                          dedup/snooze(open_loop_history) →
client_events (CTR by key)                     APNs / Telegram → history 回调

         ▲▲▲ 阈值/严重度逻辑在两侧各写一份，发散 ▲▲▲
```

### 目标（共享检测，分叉适配）

```
                    ┌─────────────────────────────────────────┐
                    │  SalienceContext  (build once, fail-soft) │
                    │  Twin overlay + DB aggregates + time      │
                    └────────────────────┬──────────────────────┘
                                         ↓
                    ┌─────────────────────────────────────────┐
                    │  salience/detectors/*  (单一真相源)        │
                    │  detect_hrv_drop / detect_lab_overdue /   │
                    │  detect_readiness / detect_adherence ...  │
                    │      ↓ list[SalientSignal]                │
                    │  { domain, signal_key, severity,          │
                    │    evidence{...}, surfaces={chip|push} }  │
                    └───────────┬──────────────────┬────────────┘
            surfaces∋"chip"     ↓                  ↓  surfaces∋"push"
         ┌──────────────────────┴───┐   ┌──────────┴───────────────────┐
         │  render_chip(signal)     │   │  render_push(signal)         │
         │  severity→priority band  │   │  severity→score              │
         │  evidence→问句 text       │   │  evidence→故事 title/body    │
         │  signal_key→生成器 key    │   │  signal_key→dedup key        │
         │  → SuggestionCandidate   │   │  → OpenLoop                   │
         └──────────┬───────────────┘   └──────────┬───────────────────┘
                    ↓                                ↓
       _select_cards (变化/随机)        settings→quiet-hours→dedup/snooze→
                    ↓                   APNs/Telegram→history（全部不变）
            chip UI + CTR               APNs + feedback
                    └────────── 统一 (domain, signal_key) 词表 ──────────┘
                                            ↓
                          observability_service: 两条漏斗可 join
```

---

## 3. 中立层数据结构

```python
# backend/app/salience/types.py
DOMAINS = {"recovery", "labs", "movement", "fuel", "vitals",
           "environment", "adherence", "data_quality", "chronic", "mental"}
# 复用 orchestrator/intent.py 的领域词表（recovery/labs/fuel/movement/...），
# 让 salience domain 与 specialist intent 对齐，未来可互相引用。

@dataclass(frozen=True)
class SalientSignal:
    domain: str            # ∈ DOMAINS
    template: str          # 选哪套文案模板（chip 问句 / push 故事）。按 signal *kind* 稳定。
                           # 例: "hrv_drop" / "lab_overdue" / "readiness_low"
    signal_key: str        # 去重身份。push 侧 (user, kind, signal_key) 不重复；chip 侧 CTR key 兜底。
                           # 可按实例变化。例: "hrv_drop" / "LDL" / "template_id=123"
    severity: int          # 0–100 归一化紧迫度（severity_base × recency/overdue 因子）
    evidence: dict         # 原始数字: {hrv_recent, hrv_prev, pct, last_value, days_since, ...}
                           # adapter 从这里模板化文案；中立层不存任何 prose
    surfaces: frozenset    # {"chip"} / {"push"} / {"chip","push"} —— 显式控制非对称（见下）
    detector: str = ""     # 来源函数名，用于日志/分析
```

**`template` 与 `signal_key` 是两件事，必须分开**（实现脚手架时浮现）：
- `template` = **渲染哪套文案**。adapter 的 copy 注册表按它 dispatch（`render_chip` / `render_push` 各一份 prose）。
- `signal_key` = **去重桶**。push 侧 `(user, kind, signal_key)` 决定重不重发。
- 对 HRV 两者恰好都是 `"hrv_drop"`，**掩盖了区别**；labs 才显出来：`template="lab_overdue"` 共用一套"该复查了"文案，但 `signal_key="LDL"` / `"HBA1C"` 各自独立去重。若只有一个 id，要么所有 lab 共用一个去重桶（漏推），要么每个 lab 写一套文案（重复）。
- ⚠️ 另一个**与 `signal_key` 同等关键**的 dedup-continuity 字段是 push 的 `kind`：它**不等于** `template`。HRV 的 `template="hrv_drop"` 但 legacy push `kind="trend_anomaly"`。`render_push` 的 `PushSpec` 把 `kind` 钉成 legacy 值，否则迁移即重置去重历史 → 重推。已有红线测试 `test_render_push_preserves_legacy_kind_and_signal_key` 守这条。

**`surfaces` 是非对称的显式开关**：
- readiness / bp / acwr / body_battery → `{"chip"}`：它们是"对话邀请"，不该半夜 push（不是必须 close 的 open loop）。
- lab_overdue / sync_stale / plan_drift / action_card_due → `{"push","chip"}`：既能主动推，也能在 chip 里作为跟进入口（**parity 收益**：现在 chip 没有"你的 LDL 该复查了"）。
- hrv_drop → `{"chip","push"}`：典型双端信号。
- 显式 surfaces 防止新增 detector 时**误开 push 通道造成 spam**。

**severity → priority band / score 映射**（必须文档化，否则两端落点漂移）：

| severity | chip priority band | push score | 说明 |
|---|---|---|---|
| ≥85 | 100（critical 必出） | ≥85 | 安全/急性 |
| 70–84 | 80–90 | 70–84 | 显著 |
| 50–69 | 60–70 | 50–69（push 噪音地板=50） | 一般 |
| <50 | 30–50 | **不 push** | 仅 chip / 数据质量 nudge |

> push 侧 `<50 不推` 的地板保留在 `render_push`/`run_open_loop_check`，**不进中立层** —— severity 是"绝对紧迫度"，"推不推"是渠道策略。

---

## 4. 迁移步骤（增量，push 侧 shadow → cutover）

### Phase 0 — 本文档评审 ✋

### Phase 1 — 脚手架 + 单信号 HRV，push 侧 shadow（零行为变更）
1. 建 `salience/` 包：`types.py`、`context.py`（先直接 `from conversation_starters import _collect_signals` 复用）、`render_chip.py`、`render_push.py`、`detectors/hrv.py`。
2. `detect_hrv_drop(ctx) -> Optional[SalientSignal]`，**一个常量** `HRV_DROP_PCT = 15`。
3. **chip 侧**：`_suggest_hrv_today` 改为 `render_chip(detect_hrv_drop(ctx))`；保持 `key="hrv_today"`（CTR 埋点连续性）。
4. **push 侧（灰度）**：`_detect_trend_anomaly` **保持 LIVE 不动**；额外用共享 detector 算一遍，`logger.info` 打 diff（shared vs live 是否一致），**不改任何 push 行为**。
5. 验收：chip 测试绿；shadow 日志连续 N 天 shared==live。

> ⚠️ HRV 两套数学不同（today-vs-7d-avg vs 7d-vs-prev-7d）。统一**只能选一个**，建议选 push 的 7d-vs-prev-7d（对单日噪声更稳；chip 现在单日坏值就触发）。这是一次**刻意的行为变更**，用 shadow 数据确认影响面再 cutover。

### Phase 2 — HRV push cutover + chip-only 信号迁移
6. shadow 一致后，`_detect_trend_anomaly` 改为走共享 detector + `render_push`。**`signal_key` 保持 `"hrv_drop"`** —— 已推过/snooze 过的用户不被重推（dedup 连续）。
7. 把 chip-only 的 Twin 信号（readiness / bp / acwr / body_battery）迁成共享 detector，`surfaces={"chip"}`。纯重构，零 push 影响。

### Phase 3 — 逐个迁移 push detector
8. `lab_overdue` / `sync_stale` / `plan_drift` / `action_card_due` 各自变共享 detector。每个：先 push 侧 shadow-diff，再 cutover，`signal_key` 字节级保持（`"LDL"` / `"garmin"` / `"template_id=123"` / `"card_id=123"`）。
9. `lab_overdue` / `sync_stale` 加 `surfaces∋"chip"` → parity 收益。

### Phase 4 — 删旧路径 + 统一埋点
10. `_GENERATORS` 与 `_detect_*` list 都变成"共享 detector + surface filter"的薄列表。删除重复阈值。
11. 统一分析：chip `client_events.meta` 与 `open_loop_history` 都带 `(domain, signal_key)` → `observability_service` 可 join 两条漏斗。

> **删代码 > 写代码**：终态 `conversation_starters.py`（现 847 行，已超 500 预算）应缩成 chip adapter + selection；检测逻辑全在 `salience/detectors/`，每文件 <500。

---

## 5. 风险

| # | 风险 | 缓解 |
|---|---|---|
| 1 | **push spam / dedup 断裂**（最高危）：`signal_key` **或** `kind` 变了 → 用户被重推已看过/已 snooze 的内容（dedup 键是 `(user, kind, signal_key)`，HRV 的 `kind="trend_anomaly"` ≠ `template`） | 两者都定为常量（`PushSpec.kind` + `signal.signal_key`）；**绝不在同一 PR 同时改 dedup 键和检测逻辑**；cutover 前 shadow-diff；红线测试 `test_render_push_preserves_legacy_kind_and_signal_key` |
| 2 | quiet-hours / settings gate 误入中立层 → chip 半夜被无故抑制 | gate 只留在 `render_push` / `run_open_loop_check`，中立层**只判紧迫度，不判渠道** |
| 3 | **声音坍塌**：共享文案 → chip 读起来像通知 | 中立层只存 `evidence`(数字)，不存 prose；chip=问句 / push=故事，各自 adapter 模板 |
| 4 | 阈值统一 = 行为变更（HRV 两套数学选一套） | 明确选 7d-vs-prev-7d；shadow 数据确认影响面；写进 changelog |
| 5 | context 构建成本：push 是 cron 扫全用户，chip 是每请求 | `SalienceContext` 保持便宜（Twin Redis 缓存 + bounded query）；per-detector 重查询 lazy 化，别让 chip 路径继承 push 的重查询 |
| 6 | severity / priority / score 三套标度漂移 | §3 映射表为唯一真相；adapter 单测覆盖边界（severity 49/50/85） |
| 7 | 文件超 500 行预算 | 迁移即拆分：`detectors/` + `render_*` 各 <500；不往 847 行的旧文件继续堆 |
| 8 | **并发 checkout 分支翻转**（见 MEMORY） | 实现全程在独立 `git worktree`：edit→pytest→commit 在隔离副本里做，不把 build+push 放进并行批次 |

---

## 6. 改动范围（实现期，仅供评审估量，本次不写）

- 新增：`backend/app/salience/{types,context,render_chip,render_push}.py` + `detectors/*.py`
- 改：`backend/app/services/conversation_starters.py`（收缩为 chip adapter + selection）
- 改：`backend/app/tasks/open_loop_manager.py`（`_detect_*` 逐个改为 detector + `render_push`；`_push_loop` 链路不动）
- 测试：`backend/tests/test_salience_*.py`（detector 正反例、severity 映射边界、两 adapter 输出形状、signal_key 连续性回归）
- 不动：`open_loop_history` schema、APNs/Telegram、feedback 回调、`/agent/conversation-starters` 响应形状

---

## 7. 评审问题（请拍板后再动手）

1. **HRV 阈值统一选哪套数学**？建议 7d-vs-prev-7d（push 现状）。是否接受 chip 由此变得对单日噪声不敏感？
2. **lab_overdue / sync_stale 加 chip surface** 是 parity 收益还是范围蔓延？本期做还是延后？
3. 迁移顺序认可"先 HRV pilot 验证 → 再 chip-only → 再逐个 push detector"吗？
4. 跨端去重（今早 push 过就不出 chip）明确**留到下一期**，认可吗？
</content>
</invoke>
