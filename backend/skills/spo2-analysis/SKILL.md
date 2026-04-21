---
name: spo2-analysis
description: 夜间血氧 SpO2 时间序列分析 — 查看逐分钟 SpO2 曲线、氧减指数 (ODI)、低氧事件统计、多夜趋势，用于睡眠呼吸暂停 (OSAHS) 筛查和夜间氧合评估。
version: 1.0.0
metadata:
  openclaw:
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
| "我有没有睡眠呼吸暂停" | 最近一晚 + 趋势 |
| "我的 ODI 是多少" | 最近一晚 SpO2 |
| "最近一周血氧趋势" | SpO2 趋势 |
| "4月18号的血氧数据" | 指定日期 SpO2 |
| "我晚上缺氧吗" | 最近一晚 + 趋势 |

Do NOT use this skill for:
- 日间血氧问题（本 skill 只有睡眠期间数据）
- 睡眠质量/睡眠时长问题（使用 sleep-deep-analysis skill）
- 心率/HRV 问题（使用 health-query skill）

## API Endpoints

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
  "sleep_end": "06:45"
}
```

**字段说明**：
- `avg_spo2`: 整夜平均血氧饱和度 (%)
- `min_spo2`: 整夜最低血氧值
- `max_spo2`: 整夜最高血氧值
- `below_90_count`: 血氧低于 90% 的采样点数
- `desaturation_events`: 氧减事件数（血氧下降 ≥3%）
- `odi`: 氧减指数 (Oxygen Desaturation Index) = 氧减事件数 / 睡眠小时数
- `data_points`: 总采样点数
- `timeline`: 逐分钟 SpO2 时间序列（用于绘图）
- `sleep_start` / `sleep_end`: 入睡/起床时间（来自 Garmin 睡眠检测）

### 2. 指定日期 SpO2 时间序列

```bash
curl -s -H "Authorization: Bearer ${HEALTH_API_TOKEN}" \
  "${HEALTH_API_URL}/spo2/me/nightly/2026-04-18"
```

与最近一晚接口返回格式相同，但查询指定日期的数据。日期格式 `YYYY-MM-DD`，使用起床日（与 Garmin 一致）。

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
1. 调 `/spo2/me/latest-night` 看最近一晚
2. 调 `/spo2/me/trend?days=14` 看两周趋势
3. 综合 ODI 均值 + nights_with_odi_above_5 评估
4. 如果多夜 ODI ≥ 5，建议进行 PSG 确诊

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
