# 基因 + 医学报告导入闭环设计 (v2)

**状态**: 草案 v2 · 2026-05-08 重写 (v1 被自我 review 打回,修 10 处)
**目标**: 一个"Agent-Native + Mobile-Native"的导入 → 解析 → 验证 → 存储 → 消化 → 复用闭环,
把目前分散在 `/upload-txt` / `/upload-pdf` / 手工表单 / medical_exam / pdf_parser 里的
半成品拼成用户能跑通的路径。

---

## §0 进场前先验证 (Iter 0)

**v1 问题: 一上来就说"后端 70% 就绪"是脑补,实际路径未验证。**

Iter 1 动工**之前**,花半天做一次代码考古,产出 `docs/IMPORT_PIPELINE_AUDIT.md`,
对每条现存路径标注 `验证过 / 假设可用 / 已废`:

| 路径 | 待验证 |
|---|---|
| `POST /genetic-data/upload-txt` | 真传一个 23andme v5 raw_data (~20MB),看解析入库 |
| `POST /genetic-data/upload-pdf` | 真传一份微基因 PDF,看能否出 variants |
| `medical_exam` 模型 + pdf_parser | 真传一份三甲医院体检 PDF,看结构化率 |
| `medical_report_ocr` | 真传一张化验单照片 |
| `medical_text_parser` | 贴一段纯文字,看 indicator 抽取 |

**产物**: 标红已废的,标黄需要修的,标绿可直接复用的。Iter 1 的 scope 按此校准,**不做幻觉规划**。

---

## §1 范围界定

### 本期覆盖 (Iter 1-3)
- ✅ 基因 raw_data (23andme / 微基因 v1-v3 / AncestryDNA)
- ✅ 体检综合报告 (结构化,字段相对规整)
- ✅ 单项化验单 (半结构化,1-3 页)

### 明确 out of scope (Phase 2+)
- ❌ 影像报告 (CT / MRI / B 超 / X 光) — 纯叙事文本,pdf_parser 处理不了,要走独立管线
- ❌ 病理报告 — 医学术语密度高,LLM 视觉也不稳
- ❌ 处方签自动识别 → 建药物档案 — 独立需求
- ❌ 多语言报告 (英文/日文体检) — 先保中文

**v1 的"医学报告"说法太宽,v2 把三类拆开明确。**

---

## §2 现状盘点 (待 §0 验证后才能定稿)

### 后端 (预估)
- `GeneticProfile` / `GeneticVariant` 模型齐
- 3 个基因上传端点 (真实状态待 §0 验证)
- Safety Guardian PGx 9 条规则已消费基因数据 (CYP2D6/CYP2C19/SLCO1B1/G6PD/HLA-B*5701/DPYD/ALDH2/MTHFR)
- FuelStrategist 用 MTHFR / APOE / FTO;MovementCoach 用 ACTN3
- PRS service 已写
- `medical_exam` + `pdf_parser` + `medical_report_ocr` + `medical_text_parser` 四服务存在 (真实状态待 §0)

### 前端
- Web `/genetic-data` 上传页 + `/medical-exams` 列表
- Mobile: **零**,没有任何导入入口

### 完全缺失
- 解析置信度 UI (OCR 失败现在静默)
- **解析失败降级路径** (v1 漏了) — 没有"让我手工贴文字"的兜底
- Agent follow-up 叙事
- 化验指标纵向趋势 (每次体检是孤岛)

---

## §3 Agent-Native 视角:"一次对话,不是三张表单"

### 目标对话 (理想态)

```
用户: [上传 23andme raw_data.txt]
AI:   收到。格式识别: 23andme v5,约 60 万位点,解析需要 1-2 分钟。
AI:   → 解析中... 38%
AI:   ✓ 完成。从中提取到我们知识库里有 action 的变异 14 条 (全集 60 万中的已知临床相关位点)。
AI:   关键发现 3 条:
      • MTHFR C677T 纯合 (TT) → 叶酸代谢效率 ~30% (置信度: 高)
      • SLCO1B1 *5/*1 杂合 → 他汀肌痛风险↑ (置信度: 高)
      • ACTN3 R/R → 爆发力型 (置信度: 中,基于单 SNP)
AI:   已更新 Fuel Strategist + Safety Guardian。要展开讲 MTHFR 吗?
```

**v1 说"30s 解析完"是乐观估计。v2 改成 1-2 分钟,并区分"全集变异数 vs 我们有 action 的变异数"(v1 用 14 这种数字含糊)。**

### 新增 Agent 工具

| 工具 | 作用 |
|---|---|
| `import_genetic_data(file_url, format_hint?)` | 调后端解析,返回 { total_variants, actionable_variants, key_findings[], confidence } |
| `import_medical_report(file_url, type_hint?)` | 体检/化验单解析,返回 { indicators[], confidence, unparsed_regions[] } |
| `list_genetic_insights(category?)` | 查询已存基因洞察,供对话叙事 |
| `list_lab_trends(loinc_code, range?)` | 纵向指标走势 (**按 LOINC code 查,不按 indicator 中文名**) |

走现有 `agent_executor.py` 的 tool-calling 框架,不开新 orchestrator 分支。

---

## §4 Mobile-Native 视角:"一个入口,三种姿势"

### 入口设计
Home → **"导入健康档案"** 一级按钮 (或 Record tab 顶部 section)

### 三种导入姿势 (v2 去掉 Share Extension 矛盾)

| 姿势 | 触发 | 交互 |
|---|---|---|
| **文件** | DocumentPicker | .txt / .vcf / .pdf |
| **拍照** | expo-camera | 一页一张,多页可拼 |
| **语音** | 麦克风 journal | "我 3 月体检 LDL 3.8" (作为兜底,非主路径) |

**iOS Share Extension 已移到 Phase 2** — v1 同时把它列入三种姿势又在决策点里说"延后",内部矛盾,v2 修掉。

### 解析中的视觉反馈
不是 spinner,是**流式文字**:

```
→ 识别文件格式...
✓ 23andme v5
→ 解析位点 (这步 1-2 分钟)...   38% ━━━━━░░░
✓ 完成
→ AI 正在为你生成解读...
```

Stream 走后端现有 SSE,不开新 channel。

### 解析失败降级 (v1 漏) — 关键

任何一步失败,必须给 Plan B,不能静默死:

| 失败场景 | 降级 |
|---|---|
| 基因文件格式不识别 | 弹窗:"这看起来不是 23andme/微基因/AncestryDNA 格式。你可以 (a) 换一个文件 (b) 手工选 3 个关键基因填" |
| PDF OCR 识别率 < 60% | 弹 OCR 原文 + "看起来不太准,你可以直接贴文字进来"的 TextArea |
| LLM 视觉超时 | 3 次重试后回落到 iOS Vision + 手工修正 |
| 整个 parse 崩溃 | 保留原始文件 48h,让用户联系客服 (log + file_id) |

### 隐私姿态
基因分区进 App 需要 **Face ID 解锁一次**,session 级保留。化验报告不锁。
**遗留 TODO**: 基因数据当前 TLS + DB 静态加密。被拖库 = 用户身份 + 疾病易感 + 药物代谢全裸。
Phase 2 做本地 E2E (SecureEnclave + passphrase 派生 key)。现在加一条 SECURITY.md 标明该风险。

---

## §5 数据闭环:7 个阶段 (v1 是 6,补了反馈)

1. **Entry** — 入口 (文件/拍照/语音)
2. **Parse** — 解析 + 置信度 + **降级路径**
3. **Verify** — 置信度 < 0.8 时用户强制修正
4. **Store** — 落库 (GeneticProfile / MedicalExam / LabIndicator)
5. **Digest** — Agent 叙事 + Specialist 触发 + Twin 失效
6. **Reuse** — 之后对话引用这份数据
7. **Calibrate** (v1 漏) — 用户发现"我另一家机构测是 CT 不是 TT"时的校准回路 → 标为"用户修正",覆盖解析结果,记录 who/when/why

**v1 6 阶段默认数据一次录入就是真理,忽略"同一基因两家公司 call 不同 rs 编号"这种真实情况。v2 补 Calibrate。**

---

## §6 LOINC 标准化 (Iter 3 硬前提,v1 漏)

### 问题
"LDL" / "低密度脂蛋白" / "LDL-C" / "低密度脂蛋白胆固醇" 在不同医院报告里混用。
Iter 3 要画"LDL 3 年走势",indicator 字段必须有稳定 ID,不能按中文名 group by。

### 方案
- `LabIndicator` 表字段:
  - `loinc_code` (string, NOT NULL) — 国际统一编码,如 LDL-C = `13457-7`
  - `display_name_zh` (string) — 报告里的原文
  - `value` / `unit` / `reference_range_low` / `reference_range_high`
  - `measured_at` (date)
  - `source_exam_id` (FK)
- 解析阶段把中文 → LOINC 的映射走:
  1. 本地字典 (常见 50 项直接命中)
  2. 不命中的调 LLM 判断并落字典 (self-learning)
  3. 都失败 → `loinc_code = "UNKNOWN"`,放 Verify 阶段让用户选

### 字典起步清单 (Iter 3 必备)
LDL-C / HDL-C / 总胆固醇 / 甘油三酯 / HbA1c / 空腹血糖 / TSH / FT3 / FT4 / ALT / AST /
γ-GT / 肌酐 / 尿酸 / 红细胞 / 白细胞 / 血小板 / 血红蛋白 / TG / 微量白蛋白 / eGFR —
约 30 项覆盖 80% 体检单。

---

## §7 5 个决策点

| # | 问题 | A | B | 推荐 |
|---|---|---|---|---|
| 1 | iOS Share Extension | 做 (多 1 周 native + App Store 审) | 延后到 Phase 2 | **B** |
| 2 | PDF 解析失败的用户修正 UI | 大 TextArea 贴文字 | 显示 OCR 原文 + 逐字段编辑 | **A** (MVP) |
| 3 | 基因分区加密 | E2E (SecureEnclave) | TLS + DB 静态加密 (现状) | **B**,**但明确是遗留 TODO** — 不是"够用",是"先这样后面补" |
| 4 | OCR 方案 | iOS Vision (免费/离线/中文已够准) | 服务端 LLM 视觉 (理解医疗上下文好) | **混合**: Vision 先扫,LLM 兜底医疗术语标注 |
| 5 | 纵向指标 | 现在就建 `LabIndicator` (绑 LOINC) | 先复用 `medical_exam.data` JSONB | **A** (Iter 3 一定要,提前建省迁移) |

**v1 #4 说"LLM 远好过 Vision"是断言,v2 改成混合方案 — Vision 负责文字提取,LLM 负责医疗术语标注 + 单位校验。成本也低一个数量级。**

### 性能预算 (v1 完全漏)

| 资源 | 上限 |
|---|---|
| 单文件上传 | 50 MB (基因 raw_data) / 20 MB (PDF) |
| 每用户每天解析次数 | 20 次 (防批量倒带 5 年体检被 LLM 视觉烧成本) |
| 并发解析 worker | 4 (Celery queue `import`) |
| LLM 视觉成本 | 单次 PDF ≤ $0.20,超过走 Vision-only |

---

## §8 3 轮迭代 MVP 拆分 (v1 Iter 2 时间低估,v2 调)

### Iter 0 — 代码考古 (0.5 天)
产出 `docs/IMPORT_PIPELINE_AUDIT.md`,对每条现存路径打标。

### Iter 1 — 统一导入入口 (~6 天,v1 说 5 天)
**目标**: 用户能从 mobile 传基因 raw_data / 体检 PDF,看到解析结果。
- Mobile: `/import` 页 + DocumentPicker + 相机 OCR
- Backend: 统一 `/api/v1/import/upload` → 按类型分发
- 流式解析进度 (SSE)
- **解析失败降级 UI** (§4 表)
- **Integration test**: 真跑一份 23andme sample + 一份体检 PDF sample 入 CI
- 性能预算落地 (速率限制 + 文件大小上限)
- **验收**:
  - 上传 23andme → 看到 actionable_variants > 0 且 key_findings ≥ 3 条 → 落库 (不是固定"14 条")
  - 上传损坏 PDF → 看到降级提示,不崩溃
  - CI integration test 绿

### Iter 2 — Agent 消化 (~10 天,v1 说 5 天)
**目标**: 上传完不是死数据,是对话。
- 新 4 个 tool schema (§3)
- **主动推送通道** (v1 没算这个) — 2-3 天工作:
  - 方案 A: 纯 APNs (麻烦,但真·主动)
  - 方案 B: 下次打开 App 时 pending message 弹出 (先做 B)
- Specialist 重跑 + Twin 失效 hook
- Face ID 保护基因分区 (1 天)
- Calibrate 阶段 UI (用户修正解析结果的回路)
- **验收**: 上传 → 下次打开 App 首屏弹"我发现你 MTHFR TT..."消息

### Iter 3 — 纵向闭环 (~7 天,v1 说 5 天)
**目标**: 多次导入构成趋势。
- `LabIndicator` 表 + LOINC 字典 (§6) — 2 天
- `list_lab_trends(loinc_code, range)` 工具
- Longitudinal Analyst 消费 LabIndicator
- Mobile 趋势图 (LDL / HbA1c / TSH 走势)
- **验收**: 连续上传 3 次体检 → LDL 走势图 + AI 评语 (不是"看到图",是"图的数据来自三份不同报告且按 LOINC 对齐")

**总计 ~24 天 (v1 算的 15 天是按顺风跑估)。**

---

## §9 Agent-Native 细节

### 被动 → 主动
导入不是"请求",是"事件"。Agent 主动说话,不是等用户问。

### Memory 旁路 (v1 没说权重)
**只写触发规则的关键发现**,不写全集:
- Safety Guardian 命中的 PGx 规则 → permanent
- FuelStrategist/MovementCoach 使用的 MTHFR/APOE/ACTN3 → permanent
- 其他 actionable variant → normal
- 未知临床意义的 → 不写入 memory,只存 DB

防止 memory 污染 (v1 隐患)。

### Specialist 触发可见
UI 显示"这次导入触发了 Safety Guardian (3 条) + Fuel + Movement",给用户"被认真对待"信号。

### Undo
15 分钟内可撤销 (软删除),超过 → 从 profile 编辑页删。

### 追溯
每条洞察 → "这条从哪来" 链接 → 显示源文件 / 解析时间 / 置信度 / rs 编号。

### 数据删除策略 (v1 漏)
账户删除时:
- 基因原始文件 **立即硬删**
- GeneticVariant 记录保留 7 天 (给用户反悔期) 后硬删
- Twin 缓存 / Specialist 审计日志同步清理
写进 SECURITY.md + privacy policy。

---

## §10 推荐起手

1. **今天**: 先做 **Iter 0 (半天)** — 真跑一遍现存路径,产出 AUDIT,拿结果校准 Iter 1 scope
2. **拿到 AUDIT 后**: 拍板是否按 §7 默认决策 (1B+2A+3B+4 混合+5A)
3. **之后**: Iter 1 动工

Iter 2/3 按 Iter 1 真实用户反馈定优先级,不提前拍板。
