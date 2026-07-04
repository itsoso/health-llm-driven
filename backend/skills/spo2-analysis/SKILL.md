---
name: spo2-analysis
description: 夜间血氧 SpO2 时间序列分析 — 查看逐分钟 SpO2 曲线、氧减指数 (ODI)、低氧事件统计、多夜趋势，用于睡眠呼吸暂停 (OSAHS) 筛查和夜间氧合评估。
version: 1.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🫁"
---

夜间血氧 (SpO2) 时间序列分析专家。基于 Garmin 手表逐分钟采样数据（~450 点/晚），提供氧减指数 (ODI)、低氧事件检测和 OSAHS 风险筛查。

## Authentication

- URL: ${HEALTH_API_URL}
- Header: `Authorization: Bearer ${HEALTH_API_TOKEN}`

## 使用场景

| 用户说 | 你应该调用的接口 |
|---|---|
| "我昨晚血氧怎么样" | 最近一晚 SpO2 |
| "看看我的夜间血氧曲线" | 最近一晚 SpO2 |
| "我有没有睡眠呼吸暂停" | 睡眠阶段×SpO2 关联分析 |
| "我的 ODI 是多少" | 最近一晚 SpO2 |
| "最近一周血氧趋势" | SpO2 趋势 |
| "4月18号的血氧数据" | 指定日期 SpO2 |
| "我晚上缺氧吗" | 最近一晚 + 趋势 |
| "深睡/REM 期间血氧低吗" | 睡眠阶段×SpO2 关联分析 |
| "哪个睡眠阶段血氧最差" | 睡眠阶段×SpO2 关联分析 |
| "睡眠阶段和血氧的关系" | 睡眠阶段×SpO2 关联分析 |

Do NOT use this skill for:
- 日间血氧问题（本 skill 只有睡眠期间数据）
- 睡眠质量/睡眠时长问题（使用 sleep-deep-analysis skill）
- 心率/HRV 问题（使用 health-query skill；分钟级心率见下方"相关 API"）

## 相关 API（跨 skill 协同）

需要做 **SpO2 × 心率对齐** 分析时（例如调查凌晨低氧是否伴随心率波动）：

```bash
# 指定日期逐采样点心率时间线 (~15 分钟一个点, 会自动降采样到 200 点以内)
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/heart-rate/me/daily/2026-05-04"
```

返回字段 `heart_rate_timeline`（每条含 `time` HH:MM 和 `heart_rate`）。
把 SpO2 timeline 和心率 timeline 按 `time` 对齐即可。

## API Endpoints

> ⚠️ **时间语义重要说明（必读）**
>
> - `record_date = D` 代表"起床那天 D"的那晚睡眠，但 Garmin 原始采样实际覆盖 `D-1 下午 ~ D 凌晨`
> - **timeline 默认已经截断到 `sleep_start ~ sleep_end` 之间**（`window=sleep`），只返回真正睡眠期间的点
> - 如果你需要包含日间零星采样（用于调查白天/睡前的血氧），加 `?window=all`，**但绝对不要对日间点做"凌晨低氧事件"之类的时间推理**
> - 响应里的 `window_start` / `window_end` 字段告诉你 timeline 实际起止时间（CST），请基于它推理，不要自己从 timestamp 加/减时区
> - 所有 `time` 字段（HH:MM）是设备本地时间（东八区），`timestamp`（毫秒）是 UTC epoch

### 1. 最近一晚 SpO2 时间序列

```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/latest-night"
```

返回最近一晚的完整 SpO2 数据：

```json
{
  "record_date": "2026-04-20",
  "summary": {
    "record_date": "2026-04-20",
    "avg_spo2": 95.3,
    "min_spo2": 88,
    "max_spo2": 99,
    "below_90_count": 3,
    "desaturation_events": 5,
    "odi": 0.7,
    "data_points": 420
  },
  "timeline": [
    {"timestamp": 1713600000000, "time": "23:15", "value": 96},
    {"timestamp": 1713600060000, "time": "23:16", "value": 95},
    ...
  ],
  "sleep_start": "23:10",
  "sleep_end": "06:45",
  "window": "sleep",
  "window_start": "23:15",
  "window_end": "06:42"
}
```

**字段说明**：
- `avg_spo2` / `min_spo2` / `max_spo2` / `below_90_count` / `desaturation_events` / `odi`: 基于 `timeline` 的 **同一子集** 统计（与 `window` 参数一致）
- `timeline`: 逐分钟 SpO2 时间序列（默认仅含睡眠期间）
- `sleep_start` / `sleep_end`: 入睡/起床时间（Garmin 睡眠检测给出）
- `window`: 本次请求的时间窗（`sleep` | `all`）
- `window_start` / `window_end`: timeline 实际起止的本地时间（HH:MM）

### 2. 指定日期 SpO2 时间序列

```bash
# 默认只返回睡眠期 timeline (推荐)
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/nightly/2026-04-18"

# 包含日间零星采样
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/nightly/2026-04-18?window=all"
```

日期格式 `YYYY-MM-DD`，使用**起床日**（与 Garmin 一致）。

### 3. SpO2 多夜趋势

```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/trend?days=7"
```

- **days**: 查询天数（1-90，默认 7）

返回：

```json
{
  "days": 7,
  "daily_data": [
    {
      "record_date": "2026-04-14",
      "avg_spo2": 95.8,
      "min_spo2": 91,
      "max_spo2": 98,
      "below_90_count": 0,
      "desaturation_events": 2,
      "odi": 0.3,
      "data_points": 400
    },
    ...
  ],
  "avg_nightly_spo2": 95.5,
  "avg_odi": 0.8,
  "nights_with_odi_above_5": 0
}
```

**字段说明**：
- `daily_data`: 每夜汇总指标列表
- `avg_nightly_spo2`: 多夜平均 SpO2
- `avg_odi`: 多夜平均 ODI
- `nights_with_odi_above_5`: ODI ≥ 5 的夜晚数（OSAHS 筛查阈值）

### 4. 睡眠阶段 × SpO2 关联分析

```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/sleep-correlation?days=7"
```

- **days**: 查询天数（1-30，默认 7）

返回每晚分阶段（deep/rem/light/awake）的 SpO2 统计 + OSAHS 风险评估：

```json
{
  "days": 7,
  "nights": [
    {
      "record_date": "2026-04-20",
      "stages": [
        {
          "stage": "deep",
          "avg_spo2": 94.2,
          "min_spo2": 88,
          "desaturation_events": 3,
          "below_90_count": 5,
          "duration_minutes": 62.0,
          "data_points": 62
        },
        {
          "stage": "rem",
          "avg_spo2": 93.8,
          "min_spo2": 85,
          "desaturation_events": 4,
          "below_90_count": 8,
          "duration_minutes": 95.0,
          "data_points": 95
        }
      ],
      "overall_odi": 1.2,
      "worst_stage": "rem",
      "apnea_risk": "normal",
      "apnea_risk_detail": null
    }
  ],
  "summary": {
    "nights_analyzed": 7,
    "avg_odi": 1.5,
    "per_stage_avg_spo2": {"deep": 94.5, "rem": 93.2, "light": 95.1, "awake": 96.0},
    "worst_stage": "rem",
    "risk_distribution": {"normal": 6, "mild": 1, "moderate": 0, "severe": 0},
    "overall_assessment": "轻度风险",
    "disclaimer": "腕表 SpO2 仅供筛查参考，确诊 OSAHS 需多导睡眠监测 (PSG)"
  }
}
```

**字段说明**：
- `stages`: 每个睡眠阶段的 SpO2 统计（平均/最低/氧减事件/低于90%次数）
- `worst_stage`: 血氧最低的睡眠阶段（通常 REM 或 deep 期间更容易出现低氧）
- `apnea_risk`: normal / mild / moderate / severe
- `per_stage_avg_spo2`: 多夜汇总各阶段平均 SpO2
- `risk_distribution`: 各风险等级的夜晚数
- `overall_assessment`: 综合评估（正常/轻度/中度/重度风险）

## 临床参考标准

### ODI (氧减指数) 分级

| ODI 范围 | 评估 | 建议 |
|---|---|---|
| < 5 次/小时 | 正常 | 无需干预 |
| 5-15 次/小时 | 轻度异常 | 建议关注，可能存在轻度 OSAHS |
| 15-30 次/小时 | 中度异常 | 建议就医，进行多导睡眠监测 (PSG) |
| > 30 次/小时 | 重度异常 | 强烈建议尽快就医 |

### SpO2 水平

| SpO2 范围 | 评估 |
|---|---|
| ≥ 95% | 正常 |
| 90-94% | 偏低，需关注 |
| < 90% | 低氧血症，需就医 |

### 低于 90% 时间占比

| 占比 | 评估 |
|---|---|
| < 5% | 正常范围 |
| 5-10% | 轻度偏高 |
| ≥ 10% | 显著异常，建议就医评估 |

## 推荐查询组合

### "我昨晚血氧怎么样"
1. 调 `/spo2/me/latest-night`
2. 重点报告 avg_spo2、min_spo2、ODI
3. 如果 ODI ≥ 5 或 min < 90，标注风险

### "我有没有睡眠呼吸暂停"
1. 调 `/spo2/me/sleep-correlation?days=14` 看两周关联分析
2. 关注 `summary.overall_assessment` 和 `summary.avg_odi`
3. 比较各阶段 SpO2：REM 期间低氧是典型 OSAHS 表现
4. 如果 `worst_stage` 是 REM 且 below_90_count 较多，说明 REM 相关低氧
5. 如果多夜 ODI ≥ 5，建议进行 PSG 确诊

### "深睡/REM 期间血氧低吗" / "睡眠阶段和血氧的关系"
1. 调 `/spo2/me/sleep-correlation?days=7`
2. 报告 `summary.per_stage_avg_spo2`：各阶段平均血氧
3. 报告 `summary.worst_stage`：哪个阶段血氧最差
4. 对比各阶段的 desaturation_events 和 below_90_count
5. OSAHS 特征：REM 期间 SpO2 明显下降、氧减事件集中

### "最近血氧变化趋势"
1. 调 `/spo2/me/trend?days=30`
2. 对比每夜 avg_spo2 和 ODI 变化
3. 关注是否有恶化趋势

## 行为规则

1. 回答**必须使用中文**
2. 先报告关键数字（平均、最低、ODI），再给解读
3. ODI ≥ 5 时**必须**提示 OSAHS 风险并建议关注
4. min_spo2 < 90 时**必须**标红提醒
5. 不要诊断 OSAHS — 明确说"腕表 SpO2 仅供筛查参考，确诊需多导睡眠监测 (PSG)"
6. 数据不足（< 3 晚）时说"数据量不足，建议持续佩戴手表监测"
7. 不要与他人的血氧数据对比
8. 夜间 SpO2 波动（如短暂下降后恢复）是正常的，不要过度解读单个低点

## 证据与局限性

- Garmin 光学 SpO2 传感器精度约 ±2%（与指夹式血氧仪对比）
- 手腕贴合度、皮肤色素、运动伪影会影响读数
- ODI 计算基于 ≥3% 下降阈值（AASM 推荐标准）
- 腕表 SpO2 不能替代医用多导睡眠监测 (PSG)，只适合初筛
- 高海拔地区 SpO2 基线偏低属正常现象
