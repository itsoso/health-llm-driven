# 设计文档:统一 canonical 归一读层(Twin / health_query 同源)

> 状态:草案,待评审
> 起因:agent `health_query(type=lab_results)` 查不到用户化验,而 Twin 能看到 —— 暴露"同一份数据存在多条不一致读路径"的结构性问题。
> 范围:agent 的数据**读取**架构(不含写入 / 不含 UI)。

---

## 1. 问题(为什么写这份文档)

用户问"查我的化验指标",`health_query` 返回空("没调到数值,请拍报告"),但同一时刻 Twin 的 labs 分区里明明有 LDL/Hcy。根因不是某一行代码,而是:

**同一份数据有多条互相不一致的读路径。**

| 读路径 | 读什么 | 问题 |
|---|---|---|
| **Twin**(`twin/builder.py` + `_collectors.fetch_latest_labs`) | 归一表 `MedicalIndicator` | ✅ 正常,能看到化验 |
| **health_query**(`agent_executor.py` 化验维度) | 原始 `/medical-exams/me` HTTP API,再经 `_api_get` **3000 字符截断成前 10 条** | ❌ 截断 + 日期窗 + 走原始表 → 查空/查不全 |

这不是孤例,是**一整类 bug**:任何"Twin 读 A 层、工具读 B 层"的地方都会在某天打架。全局 review 还发现过多套会话端点并存(legacy channel/BYO channel/一方 Agent)的同款"重复读路径"病。**"读路径分叉"是本仓库一个反复出现的主题。**

---

## 2. 设计哪里对、哪里要治

**对的(不推翻):** 两条数据通道的分法是对的,也是业界标准(RAG-over-state + tool-calling):
- **Twin = 快照**:聚合用户当前状态,开口塞进 LLM 上下文。适合"你现在怎么样"。
- **health_query = 按需查询**:Twin 是快照,装不下"LDL 半年趋势 / 所有化验项 / 最近 30 天血氧"这类历史/明细/检索。所以**需要**一个查询工具。

**要治的:** Twin 和 health_query **读的不是同一层**;且 health_query 还在**进程内 HTTP 调自己的 API**(`_api_get` → `/medical-exams/me`),多一跳序列化 + 那个 3000 字符截断黑魔法。

---

## 3. 目标架构(一句话原则)

> **一个 canonical 归一读层;Twin(快照)和 health_query(查询)都坐在它上面,谁都不绕过它去读原始表或进程内 HTTP。**

```
                      ┌──────────────────────────────┐
   LLM 上下文(快照)  │            Twin               │  twin_to_prompt_blob
        ▲             │  builder + 14 分区(Redis缓存) │
        │             └───────────────┬──────────────┘
        │                             │ 读
        │                             ▼
  ┌─────┴─────┐         ┌──────────────────────────────┐
  │ Agent LLM │         │   Canonical 归一读层(repo)    │  ← 唯一真相
  └─────┬─────┘         │  biomarker_observations /     │     · 已归一(code/单位/参考范围)
        │ tool          │  MedicalIndicator /           │     · user_id 隔离
        │ 调用          │  device_source_priority /     │     · 按 code + 日期范围查
        ▼               │  collectors / services        │     · 不截断(返回紧凑摘要)
  ┌───────────┐         └───────────────┬──────────────┘
  │health_query│────────────读───────────┘
  └───────────┘   (不再走 /xxx/me HTTP + _api_get 截断)
```

要点:
- **health_query 直接读 service/repo 层**(和 Twin 同一批读函数),不再 `_api_get` 进程内 HTTP。
- **化验/生物标志**统一读 `biomarker_observations`(P0③ 已把 `medical_indicators` 打通到这层)或 `MedicalIndicator`(二选一,以"和 Twin 同源"为准,见 §5 待定项)。
- **多源穿戴**统一经 `device_source_priority` 的 per-metric 优先级 + `multi_source_integration_service`(Twin 也用它),不另起读法。
- **输出**:LLM 友好的紧凑摘要(指标名+值+单位+日期+正常/偏高),从源头杜绝 3000 字符截断丢数据。

---

## 4. "统一走 health_query 吗"

- **查询类:是,统一走 health_query**(别再造第二个查询工具 / 第二条读路径,那就是分叉的来源)。前提:它读 canonical 层。
- **快照类:继续走 Twin**。别让 LLM 凡事都 query —— 开口就有上下文,比每次工具调用快且稳。
- 划线:**"用户当前状态"→ Twin;"历史/明细/任意检索"→ health_query**。两者读同一层,只是一个预聚合成快照、一个按需查。

---

## 5. 迁移步骤(增量,不重写)

| 步骤 | 内容 | 状态 |
|---|---|---|
| **0** | 化验维度先改读归一层 + 紧凑返回 + 放宽日期窗(止血当前 bug) | ✅ 已合(#146)—— 第 1 步样板 |
| **1** | 把第 0 步做成**统一模式**:抽 `app/services/health_read.py`(`canonical_read(db, user_id, dimension, ...)` 分发到直读 service/repo 的纯函数,返回紧凑文本;未迁维度返回 `None` → 调用方回退旧 `_api_get`),health_query 各维度走它 | ✅ 已做(本 PR)。`agent_executor._exec_health_query` 开头先调 `canonical_read`,命中即返回;化验逻辑从 executor 抽到该模块(executor -140 行) |
| **2** | 逐维度从 `_api_get`(进程内 HTTP)切到 service 层:化验 → **可穿戴** → 运动 → spo2 → … 每切一个写测试验证与 Twin 同源一致 | ✅ 化验(#146)+ 可穿戴 daily(本 PR:`activity/heart_rate/hrv/body_battery/stress` 直读 `GarminData` + `device_source_priority` 多源合并,与 Twin `MultiSourceIntegrationService` 同源)。**待迁**:运动(workout/exercise)、spo2、cgm、weight、blood_pressure、supplements、water、diet、genetic、medication |
| **3** | `_api_get` 的 3000 字符截断:留作"未归一的兜底维度"专用,归一维度不再经过它;最终能删则删 | 待定 |
| **4**(可选) | 会话端点三套合一(`OpenClawService` / `AssistantOpenClawService` 收敛),同款"读路径统一"原则 | 另立项 |

**每步可独立验证、可独立上线、可回滚。**

---

## 6. 待定项(评审要拍的)

1. **化验读 `biomarker_observations` 还是 `MedicalIndicator`?**
   - `MedicalIndicator`:Twin 现在读它(`fetch_latest_labs`),数据最全(OCR/手动/CSV 统一写入)。
   - `biomarker_observations`:归一最规范(canonical code/单位/参考范围/flag),P0③ 已把 `medical_indicators` 打通进来,且喂干预周期/PhenoAge。
   - **倾向**:`biomarker_observations`(最规范),但需确认它的回填覆盖 = `MedicalIndicator`(P0③ 的 `ensure_biomarkers`/backfill 是否已对全体用户跑过)。**否则先读 `MedicalIndicator` 保数据全,再迁。**

2. **health_read 抽到哪一层**:新建 `backend/app/services/health_read_service.py`,还是扩 `biomarker_service` + `multi_source_integration_service` 暴露统一查询接口?倾向后者(复用,不新造)。

3. **一方 Agent skill 的 health-query**(`backend/skills/health-query`)应复用同一 auth/client 上下文,避免再次产生独立读路径。长期所有查询入口都应调同一 service 层。

---

## 7. 不做(防范围蔓延)

- ❌ 不重写 Twin(快照模型是对的)。
- ❌ 不砍 health_query(查询工具是必要的)。
- ❌ 不动写入路径(本文档只谈读)。
- ❌ 不在本轮新增外部 Agent 分发 auth 模型。

---

## 8. 影响面 / 风险

- **改的是 read,user_id 隔离必须逐处保留**(canonical 层查询带 user_id 过滤)。
- 每维度迁移后,加测试断言"health_query 结果 ⊇ Twin 对应分区"(同源一致),防再次分叉。
- 紧凑摘要要控字符数(避免又触发别的截断),但**不能用"截断丢数据"换**——用"挑相关 + 聚合"而非"砍后 10 条"。
- 复杂度预算:`agent_executor.py` 已 3000+ 行,health_query 维度逻辑应抽出到 service,不要继续往 executor 堆。

---

## 9. 结论

不重新设计;**消除读路径分叉**:一个 canonical 归一读层,Twin 与 health_query 同源。当前化验修复是第 1 步样板,把它做成所有维度的统一模式即可根除这一类 bug。
