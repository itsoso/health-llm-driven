# 设计文档:个人健康预测模型(可行性 + 架构)

> 状态:草案,待评审
> 起因:用户问"能否基于个人基因/体检/可穿戴数据后训练一个个人大模型?"
> 结论:**不 fine-tune LLM**;做**小型贝叶斯预测器(人群先验 + 个人后验更新)**,输出喂进 Twin → agent 上下文。卡点是**数据采集**,不是模型方法。

---

## 1. 为什么不是"后训练一个个人 LLM"

- Fine-tune 教的是**风格/任务格式**,不是**事实**;个人健康数据是**会变的数值事实**(每天新 HRV/血糖),是 fine-tune 最差的场景(改不动、记不准、要重训)。
- 数据是**结构化数值**(SNP/化验/time-series),不是语言;数值推理该用**代码/小模型**,算完让 LLM 解读。
- 把基因组烤进权重 = 可被**训练数据提取攻击**反推,是隐私风险不是主权。
- 让 LLM"懂你"的正解是**推理时把当前状态喂进上下文**(你已有 Twin + `twin_to_prompt_blob` + RAG)。"个人模型"应是**专用预测器**,其输出进 Twin,LLM 保持可热插拔的 frontier 模型。

详见 [[设计文档:统一 canonical 读层]](design-canonical-read-layer.md) 的同源理念:个性化在**数据/上下文层**,不在权重层。

---

## 2. 数据现实(盘点实况,2026-01)

**能训的几乎是空的 —— 卡点是采集,不是方法。**

| 数据类 | 粒度 | 现状 | 够训? | 最适任务 |
|---|---|---|---|---|
| **Garmin 日聚合**(`garmin_data`) | 日级 47 字段 | ✅ User1 733 天 | ✅ | 个人基线 / 异常检测 |
| N-of-1 干预周期(`intervention_cycles`/`outcome_metrics`) | 周级,带 baseline→latest delta+status | ⚠️ 框架就绪,**0 周期** | 需 5-10 周期 | **干预效应估计** |
| CGM(`cgm_readings`) | 1-5 分钟 | ❌ 0 条 | — | 餐后血糖反应 |
| 饮食(`diet_records`) | 餐次级,带宏量 | ❌ 0 条 | — | 餐后血糖反应(配对 CGM) |
| 化验/biomarker | 单次 | ❌ biomarker 0 / exam 仅 1 天 | — | 轨迹预测(无纵向) |
| 基因(`genetic_variants`) | 静态 SNP | ❌ 0 条 | 作**特征**非时序 | 应答分层 |
| 体重/血压/睡眠/症状/补剂/打卡 | 多为 0-6 条 | ❌ | — | — |

注:细粒度采样表(`heart_rate_samples` 15min / `spo2_samples` 1min / `hrv_readings`)**已建表但未写入** → 现在只有日级,做不了分钟级任务。

---

## 3. 正确架构:人群先验 + 个人贝叶斯更新

**核心范式(N-of-1 文献验证):borrowing strength —— 单人数据少,先用人群先验,再按个人数据收缩(shrinkage)到个人后验。**

```
                ┌─────────────────────────────────────┐
   人群先验  →  │  个人贝叶斯预测器(per-user, per-task) │  → 预测值 + 不确定区间
 (默认/文献)    │  posterior = prior × 个人数据 likelihood │
                └───────────────────┬─────────────────────┘
                                    │ 写入
                                    ▼
                        Twin (新分区:predictions)  →  twin_to_prompt_blob
                                    │
                                    ▼
                            agent / specialist 解读
```

为什么对"个人健康 OS"最合适:
- **冷启动可用**:第一天没有个人数据 → 输出人群默认(带宽不确定区间)。不是"攒够数据才能用"。
- **越用越你**:个人数据累积 → 后验收缩到个人,不确定区间收窄。
- **优雅降级 + 可解释**:贝叶斯天然给**不确定度**(医疗场景必须),agent 可据此调措辞自信度(你已有 `data_confidence`)。
- **隐私友好**:小模型跑结构化数据,服务端 per-user;后验参数就是"个性化",无 LLM 权重提取风险。

参考:[Bayesian adaptive N-of-1 trials (arXiv 1911.00878)](https://arxiv.org/pdf/1911.00878) · [Personalized Nutrition by Prediction of Glycemic Responses, Zeevi/Segal, Cell 2015](https://www.cell.com/fulltext/S0092-8674(15)01481-6)(800 人 / 46898 餐建人群模型 → 个性化;**单人复刻不了,只能用人群基模型 + 个人校准**)。

---

## 4. 三阶段路线(按数据可得性排序)

### Phase 0 — Garmin 个人基线 + 异常检测【现在可做,有数据】
- **数据**:`garmin_data` 733 天(已就位)。
- **方法**:per-metric 滚动统计(均值/σ/趋势),个人 baseline + z-score 异常;无需 LLM、无需 ML 框架。
- **产出**:Twin 注入"你今天 HRV 比 90 天基线低 1.5σ / 睡眠债累积 / 训练负荷偏离"。喂 agent 解读。
- **复用**:`device_source_priority`(多源合并)、Recovery Coach。与已上线的**跨源异常(#149)** 互补(那是设备间,这是个人时间基线)。

### Phase 1 — N-of-1 干预效应估计【框架就绪,需跑周期】★最高 ROI
- **数据**:`intervention_cycles` + `outcome_metrics`(架构完整,缺周期数据)。需用户开 1 个 8-12 周干预(代谢/睡眠),每 2 周复查 → 5-8 时点。
- **方法**:**层级贝叶斯**估计个人化处理效应(personalized treatment effect),人群先验收缩。N 小也能给"这个干预对你是否有效 + 置信度"。
- **产出**:"降 LDL 干预对你 effect=−0.6mmol/L(80% CI),值得继续 / 换方案"。直接闭环你已有的 intervention_cycle。
- **为什么先做**:临床价值最高、数据需求最低、框架已就位。

### Phase 2 — 餐后血糖反应【需采集 CGM + 饮食】
- **数据**:`cgm_readings`(1-5min 餐后窗)+ `diet_records`(餐次宏量)+ 时间对齐。两条都空,需采 30-50 餐配对。
- **方法**:**人群基模型(文献/迁移)+ 个人校准**;识别个人"好/坏"食物 + 成分(纤维/蛋白比)效应。
- **依赖**:先补 CGM 接入 + 饮食日志 + 餐-血糖时间对齐机制(`Episode.meal` 当前无数据)。

---

## 5. 接入与隐私

- **接入**:新增 Twin `predictions` 分区(预测值 + 不确定区间 + 模型版本),走 `twin_to_prompt_blob` 进 agent 上下文;预测器作 service(`backend/app/services/personal_models/`),非 LLM。
- **隐私**(AGENTS.md 硬规范):per-user 后验参数,服务端;基因作特征但不外泄;喂 LLM 的是**预测结论 + 区间**(已 PII-scrub),不是原始基因/化验流。
- **不确定度优先**:任何预测必带置信区间;低置信 → agent 措辞保守 + 提示"需更多数据",对齐现有 `data_confidence`。

---

## 6. 不做(防跑偏)

- ❌ Fine-tune / 后训练 LLM 存个人健康事实(错的工具)。
- ❌ "从零在一个人身上训"——数据量不够,必用人群先验 + 个人收缩。
- ❌ 基因烤进权重(提取攻击风险)。
- ❌ 分钟级任务(细粒度采样表无数据)直到数据补齐。

---

## 7. 建议起点

1. **Phase 0 现在做**:Garmin 个人基线/异常 service(有数据、纯统计、立即有价值、喂 Twin)。
2. **Phase 1 设计先行**:N-of-1 层级贝叶斯效应估计器接 `intervention_cycle`(框架就绪),并**推动采集**(开一个真实干预周期)。
3. Phase 2 待 CGM+饮食数据补齐再启动。

一句话:**个人模型可行,但它是"人群先验 + 个人贝叶斯更新的小预测器喂进 Twin",不是 fine-tune 的个人大模型;现在先用 Garmin 数据起 Phase 0,同时为 Phase 1 攒干预数据。**
