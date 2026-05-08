# Import Pipeline Audit (Iter 0)

**日期**: 2026-05-08
**目的**: 校准 `IMPORT_PIPELINE_DESIGN.md` v2 的"~70% 后端就绪"脑补,给 Iter 1 scope 一个真实基线。
**方法**: 静态代码审计 + 调用链追踪 (未真跑样本文件,但定位到所有关键代码路径)。

---

## TL;DR

| 维度 | v2 假设 | 实际 |
|---|---|---|
| 后端 | ~70% 就绪 | **~55% 就绪** — 核心模型 + 部分 parser 可用,但有 3 处未接通 / 2 处有 bug / 4 处无 auth |
| LabIndicator 新表 | "Iter 3 要建" | **已有 `MedicalIndicator` 等价表**,字段更全,只需扩 loinc_code |
| 基因 TXT 路径 | 可用 | **真可用** — 52 个 KNOWN_SNPs + Memory KG 旁路 |
| 基因 PDF 路径 | 可用 | **有严重 bug** — 拿不到 user_id 直接 NameError 崩 (L406) |
| 医学报告 OCR 拍照路径 | "服务已存在" | **服务存在但零 caller** — 写了没接 API |
| Mobile 上传入口 | "零" | **真零** (只有查看) |
| Twin/Agent 消费 | "已消费" | **确实已消费** (基因 / 化验指标 / 体检异常项都进 Twin) |

**关键收获**: 不需要新建 `LabIndicator` 表,也不需要重写 parser,**Iter 1 重点是"接线 + 修 bug + 统一入口 + 加 Mobile UI"**,而不是建模。Iter 3 的 LOINC 化变成"给 `MedicalIndicator` 加一列"而不是"建新表 + 迁移"。

---

## §1 模型层 (绿,无需改)

| 表 | 评估 | 备注 |
|---|---|---|
| `GeneticProfile` | ✅ 完整 | user_id / test_provider / test_date / report_id / notes |
| `GeneticVariant` | ✅ 完整 | + category + risk_level + variant_nature (protective/risk/neutral) |
| `MedicalExam` + `MedicalExamItem` | ✅ 完整 | item 有 value/unit/reference_range/is_abnormal |
| **`MedicalIndicator`** (in `family_health.py`) | ✅ **字段已对齐 LabIndicator 设计** | 见下 |

### MedicalIndicator 字段清单 (对比 v2 提议)

| v2 提议的 `LabIndicator` 字段 | `MedicalIndicator` 已有 | 差异 |
|---|---|---|
| loinc_code | ❌ | **唯一缺的** |
| value / unit | ✅ value + value_text + unit | 更好 (支持影像结论) |
| reference_range_low/high | ✅ reference_low + reference_high + reference_range | 更好 (保留原始字符串) |
| measured_at | ✅ record_date | ✅ |
| source_exam_id | ✅ exam_id (FK) + report_id (FK) | 更好 (双源) |
| display_name_zh | ✅ name | ✅ |
| — | + name_en + item_code + category + is_abnormal + severity + source | 更全 |

→ **Iter 3 不需建新表,加一列 `loinc_code` 即可。迁移从"create table + backfill"变成"alter table add column + backfill"。省一半工作量。**

---

## §2 后端路径逐条验证

### 2.1 基因 TXT 上传 — 🟢 真可用

路径: `POST /api/v1/genetic-data/profiles/upload-txt`
代码: `app/api/genetic_data.py:287-356`

- ✅ 解析逻辑清楚 (tab 分隔,rsid + genotype,反向匹配 AG/GA)
- ✅ 52 个 KNOWN_SNPs 字典 (MTHFR/CYP1A2/LCT/ALDH2/VDR/ACTN3/CYP2C19/... 覆盖 FuelStrategist + Safety Guardian PGx 主要依赖)
- ✅ Memory KG 旁路 (`bulk_extract_genes_for_profile`)
- ✅ Twin 会消费 (`_collectors.py:330` 已读 GeneticVariant)

**已知局限**:
- 每行走一遍 KNOWN_SNPs dict 查找 — 60 万行 x 52 SNP lookup,预计 ~10-30s,**比 v2 假设的 1-2 分钟快**
- 只认微基因/23andMe 2 种格式,AncestryDNA / DNA Fit 格式没测

### 2.2 基因 PDF 上传 — 🟡 有 bug,会崩

路径: `POST /api/v1/genetic-data/profiles/upload-pdf`
代码: `app/api/genetic_data.py:359-517`

**bug** (必修):
```python
# L406 — _extract_genetic_from_pdf 函数内:
set_caller("genetic.pdf_vision", user_id=current_user.id)
#                                       ^^^^^^^^^^^^
# 该函数参数只有 user_id: int,没有 current_user → NameError
```

后台线程一启动就崩,PDF 路径完全不可用。profile 会建但 variants 永远不会出。

**架构问题** (非阻塞):
- 用 `threading.Thread(daemon=True)` 而不是 Celery → FastAPI worker 重启丢数据
- 每页 `time.sleep(2)` 限流,20 页要 40s+ 硬等

### 2.3 体检 PDF 上传 — 🟡 可用但无 auth

路径: `POST /api/v1/medical-exams/import/pdf`
代码: `app/api/medical_exams.py:164-271`

- ✅ pdfplumber 提取文本 + OpenAI 结构化 (`pdf_parser.py`)
- ✅ 入库 MedicalExam + MedicalExamItem + 串联生成 MedicalIndicator (`create_indicator_from_item`)
- 🔴 **`user_id: int = Query(...)` 无 auth 检查** — 任何人可给任何 user 上传体检
- 🔴 同样问题在 `/import/json` (L131)、`/import/csv` (L143)、`GET /user/{user_id}` (L117)

**Iter 1 必须修**: 改成 `current_user: User = Depends(get_current_user_required)` + 去掉 user_id 参数。

### 2.4 医学报告 OCR (拍照) — 🔴 没人调

服务: `app/services/ai/medical_report_ocr.py:45` `recognize_medical_report`
- ✅ 服务实现完整 (vision provider + system prompt + JSON 抽取)
- 🔴 **grep 全库零 caller** — 写了没接 API
- Mobile 拍照路径需要新建一个 endpoint 接这个服务

### 2.5 Medical text parser — 🟢 已接通

服务: `app/services/medical_text_parser.py`
- ✅ 有 caller (`app/api/family_health.py:745` 用 `parse_and_route`)
- 用户贴一段文字 → LLM 抽取 indicator → 落 MedicalIndicator

---

## §3 Twin + Agent 消费链 (绿,已闭环)

| 数据源 | 消费方 | 位置 |
|---|---|---|
| GeneticVariant | Twin.genetic | `_collectors.py:330` → FuelStrategist / MovementCoach / SafetyGuardian PGx |
| MedicalExam abnormal items | Twin.freshness | `_collectors.py:252` |
| MedicalIndicator (最新值) | Twin.labs | `_collectors.py:187` |
| "medical_exam" 事件 | Longitudinal Analyst narrative | `analyst.py:78` |

→ **数据一旦入库,agent 侧自动消费,不需要 Iter 2 额外接线**。Iter 2 的"Agent 消化"实际是"上传完触发 Twin 失效 + orchestrator 主动推消息",**不是**重写 specialist 读取路径。

---

## §4 Mobile 侧 (红)

- ✅ 有 `medical-exams.tsx` 列表页 + `medical-exam-detail.tsx` 详情页 (含对比)
- 🔴 **没有上传入口** — 注释 (medicalExams.ts:L7) 承认 "上传仍走 chat → OpenClaw skill, 那是 OCR 工作量太大暂不重做"
- 🔴 **没有任何基因数据页面** (list/detail/upload 全无)
- 🔴 没有 DocumentPicker / 相机 OCR 的封装

---

## §5 Iter 1 Scope 校准

基于审计,v2 v3 的 Iter 1 (6 天) 重新拆分:

### Must-do (真正的 blocker)
1. **修 bug** (0.5 天)
   - `_extract_genetic_from_pdf` 的 `current_user.id` NameError
   - 4 个无 auth 的 medical_exams endpoint 加 auth
2. **接通 OCR 服务** (0.5 天)
   - 加 `POST /api/v1/medical-exams/import/image` endpoint 调用 `recognize_medical_report`
   - 入库同 `/import/pdf` 的路径 (共用 `create_indicator_from_item`)
3. **Mobile 统一 `/import` 页** (2 天)
   - `app/import.tsx` + DocumentPicker + expo-camera
   - 类型分发 (基因 .txt → genetic/upload-txt / 基因 .pdf → genetic/upload-pdf / 体检 .pdf → medical-exams/import/pdf / 体检照片 → medical-exams/import/image)
4. **解析进度反馈** (1 天)
   - TXT / 体检 PDF 同步路径本来就秒级,不需要 SSE
   - 基因 PDF 异步路径,需要轮询 profile.notes 字段或加 `GET /genetic-data/profiles/{id}/status` endpoint
5. **解析失败降级 UI** (1 天,v2 §4 的表)
   - Mobile 端只做"失败弹手工 TextArea"一项,其他未来迭代
6. **Integration test** (1 天)
   - 用 sample 23andme / 体检 PDF 入 CI

**Iter 1 实际 6 天可交付,跟 v2 估计一致**,但内容更聚焦 (少了"新建 /api/v1/import/upload 分发端点",多了"修 bug + 接 OCR")。

### 可以延后的
- 统一 `/api/v1/import/upload` 分发端点 — v2 提议的这个其实是过度设计,每类文件类型对应的 endpoint 语义不同 (基因 vs 体检),强行统一 payload 反而复杂。Iter 1 **直接 Mobile 端按类型路由到现存 endpoint**。
- LOINC 字段 → Iter 3
- Share Extension → Phase 2

---

## §6 Iter 2/3 Scope 校准

### Iter 2 (Agent 消化)
**v2 估 10 天,实际可缩到 7 天**,因为:
- Twin 消费已经就绪 (§3) — 不用接 specialist
- 只需:
  - 上传后调 Twin 缓存失效 hook (1 天)
  - Orchestrator"主动消息"通道 — 先做方案 B (下次打开 App 弹 pending) (2 天)
  - 4 个 tool schema + agent_executor wiring (2 天)
  - Face ID 保护 (1 天)
  - Calibrate UI (1 天)

### Iter 3 (纵向闭环)
**v2 估 7 天,实际可缩到 5 天**,因为:
- MedicalIndicator 表已有,只需 `ALTER TABLE ADD loinc_code VARCHAR(20)` (0.5 天)
- LOINC 字典 (30 项) + 映射逻辑 (1.5 天)
- `list_lab_trends(loinc_code, range)` 工具 (1 天)
- Mobile 趋势图 (2 天)

**总计 Iter 1-3: 18 天 (v2 算 23 天),省 5 天,因为很多基础设施已经有了。**

---

## §7 未测 / 需要后续真跑验证

静态审计到此,以下需要 Iter 1 动工时真跑样本确认:

- [ ] 23andme v5 sample file → TXT 上传路径成功率
- [ ] 微基因 v3 sample PDF → PDF 上传路径 (修 bug 后) 成功率
- [ ] 三甲医院体检 PDF → `/import/pdf` 结构化率 (是否把肝功/肾功/血脂全抽对)
- [ ] 化验单照片 → 接通 OCR 后的识别率
- [ ] pdfplumber 对扫描版 PDF (image-only) 的降级行为 — 预计会返回空文本,需走 OCR fallback

---

## 结论

v2 设计整体方向对,但**实现量被高估**。Iter 1 真实路径是"修 bug + 接 OCR + 加 Mobile UI",不是重建。推荐:

- 今天下午就开 **Iter 1 Day 1**: 修 2 个 bug (genetic PDF NameError + medical_exams auth),半天能 ship
- 明天开始 Mobile `/import` 页

要不要我现在就开 Day 1 的 bug 修复?
