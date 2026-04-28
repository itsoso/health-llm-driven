# Health Agent Ontology

> **2026-04-28 写就**。本文档是 LLM Wiki v2 在 health 域的 schema —
> 给 LLM (specialist / extractor / orchestrator) 看的"工作手册"，
> 描述实体类型 / 关系类型 / ingest 规则 / 矛盾解决策略。
>
> 是项目的"宪法"之一 — 与 STRATEGY-2026.md 互补：
> 战略文档说"为什么"，本文档说"怎么写知识库"。

---

## 一、四层记忆架构

```
working   ┐
          ├─ MemoryFact (事实级 — subject/predicate/object 三元组)
episodic  │
semantic  │
procedural┘

          + HealthEntity (节点级 — 实体 + aliases + attributes)
          + EntityRelation (边级 — 16 种 typed predicate)
```

| 层 | 寿命 | 触发升级 | 例 |
|---|---|---|---|
| **working** | 1-3 天 | reinforcement >=3 OR conf>=0.7 | "今天 readiness=rest" |
| **episodic** | 数周 | reinforcement >=5 AND conf>=0.6 | "本周 HRV 持续偏低" |
| **semantic** | 数月-永久 | 手动或经多 case 验证 | "用户 LDL is_above 3.4" |
| **procedural** | 数月-永久 | 由 outcome_grader 直接写 | "用户对鱼油 responds_to" |

**升级路径**：每天 04:00 Celery `memory_lifecycle.run_memory_lifecycle` 自动跑。

---

## 二、实体类型 (HealthEntity.type) — 共 10 类

| type | 说明 | 例 | 默认 attributes 字段 |
|---|---|---|---|
| `medication` | 在服或历史用药 | 美托洛尔 / 倍他乐克 / metoprolol | dosage, schedule, started_at, ended_at |
| `symptom` | 主诉症状 | 鼻塞 / 头痛 / 失眠 | severity_scale (1-10) |
| `lab_value` | 化验项 | LDL / HbA1c / ALT | latest, unit, reference_low/high, last_measured |
| `vital` | 生命体征 | SBP / HRV / 体重 | latest, unit, last_measured |
| `condition` | 疾病/诊断 | 高血压 / 鼻炎 / 代谢综合征 | stage, diagnosed_at |
| `intervention` | 干预/方案 | 减重 protocol / 7天 HRV 实验 | start_date, end_date, target |
| `lifestyle_factor` | 生活方式因素 | 戒酒 / 低钠 / 早睡 | freq, intensity |
| `gene_variant` | 基因位点 | MTHFR rs1801133 CT | rs_id, genotype, gene_name |
| `supplement` | 补剂 | 鱼油 / 钙片 / VD | dosage, brand |
| `anatomical_target` | 器官/系统 (drug target / risk organ) | 肝 / 肾 / 心脏 | n/a |

**canonical_name 规则**：
- 优先用中文通用名（"美托洛尔"而非"Metoprolol"或"倍他乐克"）
- 商品名/缩写/英文进 `aliases` 数组
- 同一 user + type + canonical_name 唯一 (UNIQUE constraint)

---

## 三、关系类型 (EntityRelation.predicate) — 共 16 种

### 治疗 / 因果
- `treats`: medication → condition / symptom（"美托洛尔 treats 高血压"）
- `causes`: lifestyle / condition → condition / symptom（"高钠饮食 causes 高血压"）
- `triggers`: lifestyle / environment → symptom（"花粉 triggers 鼻塞"）
- `prevents`: lifestyle / medication → condition（"戒酒 prevents 肝功能恶化"）
- `worsens`: lifestyle → condition（"熬夜 worsens 高血压"）
- `improves`: lifestyle → condition / vital（"运动 improves HRV"）

### 相互作用
- `interacts_with`: medication ↔ medication / supplement
- `contraindicates`: condition → medication（"哮喘 contraindicates 美托洛尔"）

### 结构
- `depends_on`: 下游依赖上游
- `is_part_of`: 局部 ⊂ 整体
- `is_a`: 子类 ⊂ 父类（"美托洛尔 is_a beta_blocker"）

### 用户态
- `owns`: User → entity（"我 owns 美托洛尔"）— 表达"在用/有"
- `responds_to`: User → intervention（用户对该干预**有效**）
- `does_not_respond_to`: User → intervention（**无效**）
- `exposed_to`: User → lifestyle_factor / trigger（"暴露于 PM2.5"）

### 知识管理
- `supersedes`: 新 entity 取代旧 entity（旧药停用 → 新药）
- `contradicts`: 两条关系矛盾 (具体规则见"矛盾解决")
- `associated_with`: 弱关联 (无明确因果，但相关)

---

## 四、Predicate 默认 decay_rate (memory_facts)

| predicate | decay_rate | 半衰期 | 说明 |
|---|---|---|---|
| `has_genotype`, `has_history` | 0.0 | ∞ | 永不衰减 (基因/家族史) |
| `takes_medication`, `treats`, `responds_to` | 0.005 | ~140 天 | 慢衰减 (慢病诊断, 长期患者特征) |
| `is_value`, `is_above`, `is_below`, `equals` | 0.03 | ~23 天 | 中等 (近期状态 / 化验) |
| `triggers`, `worsens`, `improves` | 0.05 | ~14 天 | 快衰减 (临时症状/触发) |
| 其它 | 0.02 | ~35 天 | 默认 |

reinforcement floor: `min(0.4, 0.05 × count)` — 反复出现的 fact 不会完全归 0。

---

## 五、Ingest 工作流

### 1. 自动 ingest 源 → 哪类记忆

| 源 | 触发点 | 入哪个 tier | 抽哪些 entities |
|---|---|---|---|
| Specialist Finding (raw) | orchestrator 跑完 | working facts | 触发自动 KG 抽取 (zone, ACWR, stage 等) |
| ActionCard outcome (graded) | outcome_grader 评分后 | procedural facts | 关联 `User → responds_to → intervention` |
| MedicalIndicator (异常) | medical_exam 解析 | semantic facts | `User → owns → lab_value` (含 attributes.latest) |
| UserDirective | telegram_webhook / 手动 | semantic facts (decay=0) | n/a |
| Medication | 用户添加用药 | n/a | `User → owns → medication` (KG only) |

### 2. Ingest 时的去重 / 合并

**MemoryFact** (`memory_service.write_fact`)：
- 同 (user, subject, predicate, object_value) → 触发 `reinforce_fact` 而非新建
- confidence + 0.05, reinforcement_count + 1, last_reinforced_at = now
- sources 数组 append (保留所有来源)

**HealthEntity** (`kg_service.upsert_entity`)：
- 同 (user, type, canonical_name) → 合并 aliases (集合去重) + attributes (新覆盖旧)
- confidence 取 max
- sources append

**EntityRelation** (`kg_service.create_relation`)：
- 同 (user, subject, predicate, object) → evidence_count + 1, confidence 增强
- 自环 (subject == object) 直接拒绝

---

## 六、矛盾解决策略

### 自动检测 (`memory_service.detect_contradictions`)
矛盾 predicate 对：
- `is_above` ↔ `is_below`
- `responds_to` ↔ `does_not_respond_to`
- `causes` ↔ `prevents`

### 处理优先级（写新 fact 时）
1. **新 source 权重 ≥ 旧 source 总权重** → `supersede_fact(old.id, new.id)` 旧 fact 归档
2. **新 source 权重 < 旧** → 新 fact 暂不入库，记 audit log 让用户决定
3. **同时间多 source 矛盾** → 都保留 + 关系 `contradicts` 标注（后续由 specialist 在 prompt 中明示）

cross_review 路径中遇到矛盾，optionally 触发 LLM 仲裁（成本高，仅 hard 冲突时启用）。

---

## 七、Hybrid Search 行为约定

`hybrid_search.hybrid_retrieve(query)` 的检索流：
1. 全 user corpus = active memory_facts ∪ active entities
2. BM25 (中文 char + 2/3-gram) → top 20
3. Graph 2-hop from mentioned entities → top 20
4. RRF (k=60) 融合 → top_k

调用方应：
- 简短 query (< 200 字) 直接传
- 长 prompt 取头部 300 字作 mention 检测
- 检索结果按 `source_type` 分组渲染 ("📋 事实" / "🔗 实体")

---

## 八、隐私 / 敏感性

| 标志 | 字段 | 处理 |
|---|---|---|
| `is_private` | MemoryFact | 默认 true. false 仅用于聚合统计 |
| `is_sensitive` | MemoryFact | true → Sentry breadcrumb / 第三方上传时 redact |
| sensitive 范围 | 用药 / 基因 / 心理诊断 / 性病史 | extractor 设置 is_sensitive=true |

---

## 九、什么不应进 wiki

- **临时聊天对话** — 用 `clinical_journal_entries` (SOAP) 而非 fact
- **未确认的猜测** — confidence < 0.3 不进库
- **来自不可信源** — 必须有 source 字段，无 source 拒绝
- **生命体征瞬时值** — 用 GarminData 时序表，不进 wiki
  （进 wiki 的是聚合后的趋势 fact: "HRV 7 天均值偏低"）
- **PII** — 真名/手机/邮箱不入库

---

## 十、维护操作清单

| 任务 | 频率 | Cron |
|---|---|---|
| Decay + crystallization | 每天 04:00 | `memory-lifecycle` |
| Stale entity 软删 (90 天没 source) | 每天 04:00 (同上) | 同上 |
| Knowledge base ChromaDB rebuild | 每周一 04:00 | `rebuild-knowledge-index` |
| Specialist hit-rate 评分 | 每天 08:00 | `grade-action-cards` |

---

## 修订日志

- 2026-04-28: 首版. 配合 LLM Wiki v2 阶段 A-D 上线.
