# External Health Knowledge Integration PR0 Reviewed Gates

日期: 2026-06-26
状态: PR0 reviewed-only gate 与 high-risk golden slices 已落地，本文作为后续知识库接入的执行基线。
范围: 运动、饮食、补剂、睡眠、胃病治疗、慢性鼻炎治疗、基因解析等外部健康知识进入 Reva 系统的治理路径。

## 1. 决策

外部健康知识不直接进入运行时问答。

运行时权威顺序为:

1. 本地 reviewed system KB / domain table。
2. 代码内确定性 safety/domain rule。
3. 外部 API、bulk data、MCP、搜索结果只进入 draft/review 工作台，不作为医疗建议直接引用。

引入路径为:

```text
official / curated source
  -> importer / connector / optional MCP tool
  -> draft artifact
  -> reviewer gate
  -> local Postgres KB / domain table
  -> retrieval / evidence resolver / eval gate
```

搜索适合做发现和补漏，不能做运行时权威。MCP 适合作为 Reva 自己的受控工具层，暴露已治理的本地知识、source refresh、coverage report 和 eval runner，而不是把第三方 MCP 输出直接喂给健康 agent。

## 2. 当前基线

已存在的系统 KB 形态:

- 种子目录: `backend/data/system_kb_v2_seed/`
- 服务层: `backend/app/services/system_knowledge_service.py`
- 导入层: `backend/app/services/system_knowledge_importer.py`
- eval runner: `backend/app/services/system_knowledge_eval.py`
- serving gate: 仅 `review_status=reviewed` 且未 archived 的文档可进入 search/lookup/bundle。
- retrieval: lexical/BM25 + FTS fallback + `kb_document_vectors` sparse vector table + graph RRF；search response shape 保持不变，后续可把稀疏向量表替换为 pgvector embedding 列。
- coverage report: admin coverage report 已输出全局文档/外部证据/运营 unsupported 指标，并按 domain 输出 source coverage、review status、eval coverage、stale/decay risk。
- draft extraction gate: LLM/importer 生成内容先写入 `draft_manifest.json` + draft artifact；`validate_artifact_review_gate` 在 artifact 层阻断 serving，只有 `review_draft_artifacts` 写入 reviewer audit 并提升为 reviewed 后才允许导入。

本批 PR0 后 reviewed seed 覆盖:

| artifact | count |
| --- | ---: |
| entities | 226 |
| claims | 440 |
| relations | 3277 |
| eval_cases | 37 |
| contraindications | 36 |

已覆盖的 high-risk golden slice:

- 胃病/反流/鼻炎重叠: GERD/LPR、报警特征、长期抑酸用药边界、鼻炎反流重叠。
- H. pylori/消化性溃疡: HP 状态分流；HP 阳性时仅触发医嘱、复查和资料整理，不生成根除方案。
- 胃病用药安全: 胃病/溃疡史合并 NSAID 与抗凝/抗血小板的出血风险；长期 PPI/P-CAB 的适应证复核和监测闭环。
- 睡眠: 夜间低氧/ODI 升高升级为睡眠呼吸评估，禁止用加大训练替代；失眠进入 CBT-I 和睡眠医学边界；镇静药合并酒精或低氧进入医生/药师/睡眠中心复核禁区。
- 运动: 发热/疑似感染时训练目标降级，禁止带病加量；运动中胸痛/晕厥/心率异常进入停止训练和医生/急症分诊边界；低恢复/Training Readiness 很低时训练降级。
- 饮食: 高钠饮食与血压偏高只做食物来源识别和家庭血压趋势，禁止调药或极端限盐；糖尿病极端控碳/禁食、CKD 高蛋白或极端去蛋白、痛风/高尿酸快速减重和脱水、高血压合并 CKD/保钾用药时钾盐替代进入医生/营养师复核边界。
- 慢性鼻炎: 鼻喷激素/盐水冲洗/抗组胺依从性复盘，禁止自行升级鼻炎用药或长期依赖减充血剂；鼻窦炎样红旗、鼻炎-哮喘重叠、过敏原免疫治疗/脱敏治疗进入耳鼻喉科/过敏科/呼吸科转诊或复核边界。
- 基因/PGx: TPMT/NUDT15 硫嘌呤；CYP2C19 氯吡格雷/PPI；DPYD/氟嘧啶；SLCO1B1/他汀；HLA-B*15:02/卡马西平或奥卡西平；CYP2C9/VKORC1/华法林；HLA-A*31:01/卡马西平；HLA-B*58:01/别嘌醇；G6PD/高风险氧化性药物。
- 补剂: 维生素 D/eGFR/血钙；镁与吸收相关用药；Omega-3 与抗凝/抗血小板；咖啡因与睡眠不足；益生菌与免疫抑制；褪黑素与镇静药叠加。

## 3. 专业知识库接入策略

### 3.1 运动

优先源:

- ACSM / CDC / WHO 体力活动指南。
- AHA/Mayo 等公开临床安全边界资料。
- 运动医学、睡眠呼吸、急性病训练限制相关指南。

落地方式:

- 低风险训练原则进 reviewed claim。
- 急性病、胸痛、低氧、晕厥、发热等进 contraindication。
- 与 wearable/Twin 条件绑定，必须有 eval case。

### 3.2 饮食

优先源:

- Dietary Guidelines for Americans、AHA/ACC 高血压、KDIGO/ADA 等官方指南。
- USDA FoodData Central 可作为营养成分 bulk/source table。

落地方式:

- 可量化成分数据进入本地 domain table。
- 行为建议进入 reviewed claim。
- 药物、疾病、极端限制相关场景进入 contraindication。

### 3.3 补剂

优先源:

- NIH ODS supplement fact sheets。
- NCCIH、FDA safety communication。
- LiverTox / Micromedex 类安全资料只在许可允许范围内转化。

落地方式:

- 成分、剂量上限、相互作用风险应拆为 structured table + KB claim。
- 禁止运行时直接生成补剂叠加、替药、治疗疾病的建议。

### 3.4 睡眠

优先源:

- AASM guideline。
- 睡眠呼吸、CBT-I、PAP 相关指南。
- 可穿戴指标只能作为筛查/趋势线索。

落地方式:

- 睡眠卫生可作为低风险 claim。
- 低氧、ODI、严重白天嗜睡、驾驶风险、镇静药等必须走 contraindication 和医生评估边界。

### 3.5 胃病治疗

优先源:

- ACG GERD / H. pylori / dyspepsia 相关指南。
- NICE/AGA 等可作为 cross-check。

落地方式:

- GERD 生活方式、报警特征、长期抑酸监测、HP 状态分流、HP 阳性医嘱边界进入 reviewed KB。
- 不写药物组合、抗菌剂量、疗程或替代医生治疗方案。

### 3.6 慢性鼻炎治疗

优先源:

- AAO-HNS allergic rhinitis guideline。
- AAAAI/ACAAI rhinitis practice parameter。
- MedlinePlus/FDA 用于非处方药安全边界。

落地方式:

- 鼻腔冲洗、诱因记录、依从性复盘进入 claim。
- 减充血剂过度使用、单侧/出血/面痛/嗅觉改变、哮喘加重进入 contraindication。

### 3.7 基因解析

优先源:

- CPIC guideline。
- PharmGKB annotations。
- ClinVar/ClinGen 用于变异临床意义，但必须做许可和解释边界。

落地方式:

- PGx 高风险药物先做 golden slice: CYP2C19、TPMT/NUDT15、SLCO1B1、DPYD、HLA-B、CYP2C9/VKORC1。
- DTC/消费级结果只作为提醒医生/药师复核，不直接触发诊断、剂量或换药。

## 4. 实施顺序

1. PR0 reviewed-only gate: 已完成。
2. High-risk golden slices: 胃病/HP、PGx、睡眠、运动、饮食、鼻炎、补剂本批 PR0 已覆盖。
3. Coverage report: 已完成，每个 domain 输出 source coverage、review status、eval coverage、stale/decay risk。
4. Draft extraction: 已完成。LLM 只能生成 draft artifact；必须经过 reviewer gate 才能进入 serving。
5. Real vector backend: 已完成。用 `kb_document_vectors` 等价向量表替换 deterministic semantic alias stream，并保持 search response shape。
6. Mobile evidence UI: 已完成。共享 `EvidenceRefsRow`、`ClaimSheet` 与系统知识卡片统一展示 reviewed evidence refs、claim boundary 和 contraindication 命中；饮食、补剂、运动卡片透传同一套 evidence props。
7. Release gate: 已完成。`backend/scripts/run_external_health_knowledge_release_gate.py` 统一执行 domain focused tests、隔离 JSONL lint/import + system KB eval runner、compileall。

## 5. 验收闸门

新增外部健康知识必须满足:

- `metadata.review_status == "reviewed"` 才能被 serving search/lookup 返回。
- 每个 high-risk claim 至少有一个 source、claim boundary、applies_when 或明确的 entity link。
- 涉及药物、治疗、诊断、急症、基因解读的知识必须配套 contraindication。
- 每个新 high-risk slice 必须有 eval_case，且 eval runner 为 0 failed。
- 运行时回答只能引用 reviewed local KB；外部搜索/MCP 输出只能进入 draft/review。
- 用户健康数据查询继续遵守 user isolation、审计、脱敏和最小权限。

## 6. 下一批 backlog

当前 PR0 high-risk golden slice backlog 已清空，Coverage report、draft extraction gate、real vector backend、mobile evidence UI 与 release gate 自动化均已落地。后续外部知识接入应从新增 source/domain slice 的 reviewed artifact 和 eval case 开始。

2026-06-27 后续 slice 进展:

- 补剂安全: 圣约翰草/贯叶连翘与抗抑郁药、口服避孕药、华法林、免疫抑制剂、抗病毒药或部分抗肿瘤药同现时，进入医生/药师相互作用复核边界；已按 reviewed claim + contraindication + eval case 形态接入。
