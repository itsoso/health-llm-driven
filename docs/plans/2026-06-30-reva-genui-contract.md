# Reva GenUI 契约 — AI 回答里渲染固定模板的动态组件(图表/卡片/表格)

> Status: **Plan + 实施中(Phase 1+2 MVP 已开工)**
> Date: 2026-06-30
> Owner: Reva / Personal Health OS
> 缘起:AI 被要求"绘制 HRV 曲线"时,只能吐 ASCII 假图,**且数字是 LLM 编的**(非真实 Garmin 数据)。
> 关联:`docs/plans/2026-06-27-real-world-task-execution-ios-strategy.md`(同属"AI 输出结构化产物")· P5 ReorderIntent(确定性 + 逐笔确认范式)· 通知 deep_link(能力协商先例)。

---

## 0. 一句话

把 AI 回答从"自由 markdown/ASCII"升级为 **固定组件目录 + LLM 选模板 + 确定性代码填真数据 + 客户端按注册表原生渲染**(业界叫 Generative UI / Server-Driven UI)。

---

## 1. 业界对标(GitHub 已产品化,验证方向)

| 方案 | 形态 | 借鉴 |
|---|---|---|
| Vercel `json-render`(2026) | AI 生成界面但**约束在你定义的组件**,护栏+可预测 JSON+流式+跨端(React/Vue/RN) | 组件白名单 + 跨端契约 |
| Google `A2UI`(2026) | 声明式 JSONL 流,组件扁平列表,LLM 增量生成,web/移动/桌面原生渲染,跨信任边界 | "LLM 只发声明不发代码" + 能力协商 |
| Vercel AI SDK 3.0 / assistant-ui | tool-call→组件;agent 只发**白名单组件**非裸代码 | 安全:白名单=allow-list |
| Thesys C1 / GPT-Vis(AntV) | 内置表格/图表,原生 Vega-Lite | 图表语法别自创,取 Vega-Lite **形** |
| shadcn registry + Zod | schema 定义目录,LLM 产受约束 JSON | catalog + schema 校验 |

**五点共识**:① 受约束组件目录(非自由代码)② 声明式 JSON(信任边界)③ 流式渐进 ④ 一份 spec → 多端渲染 ⑤ 图表用声明式语法。

## 2. 对健康致命的分歧点(本契约的核心差异)

通用框架默认 **LLM 填数据** —— 对健康是红线(截图里 `63ms` 是编的)。

> **铁律:LLM 只选模板 + 给查询参数 + 写叙事;数据由确定性代码查真值填入。** 缺数据显"数据不足",绝不补点。契合本仓库"确定性数据 + LLM 合成"不变量与 R4。

## 3. 架构

```
用户:"绘制我最近半年的 HRV 曲线"
   ↓  classify_intent + 图表意图检测(确定性正则:绘制/画/趋势/曲线 + 已知 metric)
   ↓  build_chart_series(user, metric, range)   ← 确定性查真实日级序列(twin/garmin_timeseries/indicator)
   ↓  [能力协商] 客户端声明 genui-v1 / genui-components-v1 ?
        ├─ genui-components-v1 → 后端确定性拼 metric_line_chart(真 data)+ 简短叙事
        ├─ genui-v1 → 后端确定性拼旧 line_chart(真 data)+ 简短叙事
        └─ 否 → 现状(markdown 表/文本),零回归
   ↓  客户端按注册表渲染:Mac Web;Web React;Mobile RN(自绘 SVG / svg 复用)
```

### 3.1 组件目录 v0(小而固定)
`metric_line_chart` / `line_chart`(先做)→ 后续 `metric_grid` / `table` / `timeline` / `comparison` / `alert_list` / `action_card`。
- 图表取 **Vega-Lite 的形**但 v0 用**最小自定义 schema**(各端可手绘 SVG,离线稳),不强依赖 vega 运行时。

### 3.2 `reva-ui` 块契约 v0(line_chart)
后端确定性产出(嵌在 assistant 消息里的 fenced block):
```
​```reva-ui
{"v":1,"component":"line_chart","title":"最近半年 HRV 趋势","unit":"ms",
 "x":["1月",...],"series":[{"name":"日均HRV","points":[63,59,...]}],
 "annotations":[{"x":"4月","label":"波动大","kind":"warn"}],
 "y_hint":{"min":0},"source":"garmin","data_note":"基于 N 天真实数据"}
​```
```
- `points` 由 `build_chart_series` 真查;LLM 只可写 `annotations.label` 与块外叙事。
- 解析端用 `json_lenient.lenient_loads`(已上线)兜底。

### 3.2.1 `metric_line_chart` v1(通用指标趋势组件)
新客户端声明 `genui-components-v1` 后，后端返回显式 schema:
```
​```reva-ui
{"v":1,"schema":"reva.metric_line_chart.v1","component":"metric_line_chart",
 "metric":"resting_hr","range":"6m","title":"静息心率趋势","unit":"bpm",
 "x":["06-24","06-25"],"series":[{"name":"Apple Watch 静息心率","role":"device","points":[61,59]}],
 "annotations":[{"x":"06-25","label":"最新 59 bpm · Apple Watch","kind":"latest"}],
 "source":"garmin","data_note":"基于 N 天真实数据"}
​```
```
- 当前确定性 allowlist: `hrv`、`resting_hr`(含自然说法“心率”)、`stress`、`sleep`、`sleep_score`、`steps`、`body_battery`、`weight`。
- Mobile parser 把 component 映射为 card descriptor；renderer 由卡片 registry 选择。未知 component fail-closed。
- `line_chart` 保留为旧客户端兼容协议。

### 3.3 能力协商(防移动端回归)
- 客户端发 `X-Reva-Client-Caps: genui-v1`(或等价 query)声明支持基础 `reva-ui` fenced block。
- 客户端再声明 `genui-components-v1` 时，后端返回显式 schema 的动态组件，如 `metric_line_chart`。
- 后端仅对声明者发 `reva-ui`;否则现状。**渐进上线、按端开关。**
- 未知 component / 解析失败 / 弱模型 → 降级 markdown 表,绝不白屏/不显示裸 JSON。

### 3.4 弱模型(截图是 Qwen3.7 Max)
- **MVP 不让 LLM 吐结构**:块由后端确定性拼,LLM 只写叙事 → 规避弱模型结构化不稳。
- 后续若让 LLM 选更多组件:tool-calling + `lenient_loads` 兜底 + 模型门控(弱模型降级)+ eval 钉选型。

## 4. 分期

| 阶段 | 内容 | 状态 |
|---|---|---|
| **P1 契约 v0**(本 PR) | `reva-ui` line_chart schema + `build_chart_series` 确定性真查 + 图表意图检测 + 能力协商 + 降级 + 测试 | **实施中** |
| **P2 Mac 渲染**(本 PR) | 聊天 WebView JS shell 拦 `reva-ui` fence → 自绘 SVG 折线(tooltip,离线)+ 发 caps 头 | **实施中** |
| P3 Web React 渲染器 | 同契约,React(可吃 json-render) | 待 |
| P4 Mobile RN 注册表 | 复用 `indicator-history` 的 react-native-svg 图；Mobile 已声明 `genui-v1, genui-components-v1` 并渲染 `metric_line_chart` / `line_chart` fenced block | 已推进 |
| P5 扩目录 | metric_grid/table/timeline/comparison;同契约渲染现有 safety/specialist/action-card 结构化输出 | 待 |
| 贯穿 | **数据确定性闸**:数字永不来自 LLM;缺数据显"数据不足";旧端降级 | 必须 |

## 5. 硬边界 / 风险
- **别只修渲染不修数据源** —— 否则把假数据画得更可信(更危险)。第一优先 = 图的数字 = 真查询结果。
- 能力协商保证移动/Web 旧端零回归(只 Mac 先上)。
- 不让 LLM 产可执行代码,只产受 schema 约束的声明 JSON(信任边界)。

## 6. 现状(2026-06-30 起)
P1+P2 MVP 开工:Mac 上"绘制 HRV 曲线"→ 真实日级 HRV 折线图内联渲染。P4 Mobile 已接入 `genui-v1, genui-components-v1` 能力声明与 `metric_line_chart` / `line_chart` 原生渲染；“心率/睡眠评分/步数/身体电量”等指标已走确定性真数据路径。其余 Web 与扩展组件按 §4 推进。
