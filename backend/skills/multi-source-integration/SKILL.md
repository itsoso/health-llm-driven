---
name: multi-source-integration
description: Integrate multi-source health data — unified timeline from Garmin (minute-level), diet (meal-level), labs (month/year), and genetics (one-time). Cross-modal correlation analysis, data completeness reporting, and integrated health profile generation.
version: 1.0.0
metadata:
  agent:
    requires:
      env: [HEALTH_API_URL, HEALTH_API_TOKEN]
      bins: [curl]
    primaryEnv: HEALTH_API_TOKEN
    emoji: "🔗"
---

你可以整合用户来自多个数据源（Garmin 可穿戴、饮食记录、体检报告、基因检测、体重秤等）的健康数据，生成综合健康画像、数据完整性报告、以及跨模态关联分析。

## Authentication
- URL: $HEALTH_API_URL
- Header: `Authorization: Bearer $HEALTH_API_TOKEN`

## Available Endpoints

### 1. 综合健康画像
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health/integration/profile"
```
返回整合所有数据源的统一健康快照：
```json
{
  "user_summary": {
    "name": "张三",
    "age": 35,
    "gender": "男",
    "data_sources": ["garmin", "diet", "weight", "basic_health", "genetic"]
  },
  "latest_metrics": {
    "garmin": {
      "date": "2026-04-04",
      "resting_hr": 62,
      "hrv": 55.2,
      "sleep_score": 78,
      "steps": 8520,
      "stress_level": 35,
      "body_battery_current": 72
    },
    "body_composition": {
      "date": "2026-04-03",
      "weight": 72.5,
      "bmi": 23.8,
      "body_fat_pct": 18.5
    },
    "labs": {
      "date": "2026-03-15",
      "total_cholesterol": 5.2,
      "blood_glucose": 5.1,
      "blood_pressure": "125/78"
    },
    "diet_today": {
      "total_calories": 1850,
      "protein_g": 95,
      "meals_logged": 3
    },
    "genetic_highlights": ["MTHFR CT(叶酸代谢轻度减弱)", "CYP1A2 快代谢(咖啡因)"]
  },
  "health_narrative": "35岁男性，BMI正常(23.8)，心率变异性中等(55ms)，睡眠质量良好(78分)。近期体检血脂正常，血糖正常。基因提示叶酸代谢轻度减弱，建议关注叶酸摄入。",
  "data_freshness": {
    "garmin": "1天前",
    "weight": "2天前",
    "labs": "21天前",
    "diet": "今天",
    "genetic": "一次性数据"
  }
}
```

### 2. 数据完整性报告
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" "$HEALTH_API_URL/health/integration/completeness"
```
返回各数据源覆盖率和缺失分析：
```json
{
  "overall_completeness": 0.72,
  "sources": {
    "garmin": {
      "status": "活跃",
      "coverage_30d": 0.93,
      "total_records": 285,
      "last_update": "2026-04-04",
      "missing_days_30d": 2,
      "key_metrics": {
        "heart_rate": {"coverage": 0.97, "status": "充足"},
        "sleep": {"coverage": 0.90, "status": "充足"},
        "hrv": {"coverage": 0.85, "status": "充足"},
        "spo2": {"coverage": 0.60, "status": "部分"}
      }
    },
    "diet": {
      "status": "部分活跃",
      "coverage_30d": 0.45,
      "total_records": 42,
      "last_update": "2026-04-04",
      "avg_meals_per_day": 1.4,
      "recommendation": "建议每天记录3餐以提高营养分析准确度"
    },
    "weight": {
      "status": "活跃",
      "coverage_30d": 0.80,
      "total_records": 120,
      "last_update": "2026-04-03"
    },
    "basic_health": {
      "status": "低频",
      "total_records": 3,
      "last_update": "2026-03-15",
      "staleness_days": 21,
      "available_metrics": ["血压", "血脂", "血糖", "BMI"],
      "missing_metrics": ["腰围", "肝功能", "肾功能"]
    },
    "genetic": {
      "status": "已录入",
      "total_variants": 17,
      "categories": ["nutrition", "exercise", "drug_sensitivity", "disease_risk", "sleep"]
    }
  },
  "recommendations": [
    "饮食记录不足，建议每天记录3餐",
    "体检数据已21天未更新，建议定期录入",
    "缺少腰围数据，影响代谢综合征评估准确度"
  ]
}
```

### 3. 跨模态关联分析
```bash
curl -s -H "Authorization: Bearer $HEALTH_API_TOKEN" \
  "$HEALTH_API_URL/health/integration/correlations?days=30"
```
可选参数：`days` — 分析窗口天数（默认30，最大90）

返回跨数据源的关联发现：
```json
{
  "period": "近30天",
  "correlations": [
    {
      "finding": "高蛋白饮食日 → 次日HRV偏高",
      "source_a": "diet",
      "source_b": "garmin",
      "metric_a": "蛋白质摄入 >100g",
      "metric_b": "次日HRV",
      "direction": "正相关",
      "occurrences": 8,
      "strength": "中等",
      "evidence_level": "D级(个人观察)"
    },
    {
      "finding": "睡眠分数与次日步数正相关",
      "source_a": "garmin_sleep",
      "source_b": "garmin_activity",
      "metric_a": "睡眠分数 >80",
      "metric_b": "次日步数",
      "direction": "正相关",
      "occurrences": 12,
      "strength": "较强",
      "evidence_level": "D级(个人观察)"
    }
  ],
  "sample_size": 30,
  "caveat": "关联分析基于个人数据的简单统计，不代表因果关系。样本量小，结论仅供参考。"
}
```

## Data Contract

### 输入依赖
本 Skill 整合以下模型数据：
1. **GarminData** — 分钟级穿戴数据（心率、睡眠、步数、压力、HRV、血氧）
2. **DietRecord** — 餐次级饮食记录（卡路里、宏量营养素）
3. **BasicHealthData** — 月/年级体检数据（血压、血脂、血糖）
4. **WeightRecord** — 日级体重/体脂数据
5. **GeneticVariant** — 一次性基因检测数据
6. **DiseaseRecord** — 疾病史
7. **User** — 基本信息（年龄、性别）

### 时间粒度对齐
| 数据源 | 原始粒度 | 对齐粒度 |
|--------|---------|---------|
| Garmin | 分钟 | 天（取日均值） |
| 饮食 | 餐次 | 天（汇总日摄入） |
| 体重 | 天 | 天 |
| 体检 | 月/年 | 不变（最新值） |
| 基因 | 一次性 | 不变（永久有效） |

### 输出格式
- 所有回复使用中文
- 数据新鲜度明确标注
- 关联分析附带证据等级和样本量
- 缺失数据给出具体改善建议

## When To Use

**使用场景：**
- 用户询问"我的整体健康状况怎么样"
- 用户想了解数据记录的完整性和覆盖率
- 用户想发现不同数据之间的关联（如饮食↔睡眠）
- 用户有多个数据源，想要交叉验证或综合分析
- 其他 Skill 需要调用综合画像作为上下文

**不要使用：**
- 用户只查询单一指标（用 health-query skill）
- 用户只想记录数据（用 health-record skill）
- 用户专门问慢病风险（用 chronic-risk-assessment skill）
- 用户专门问运动建议（用 workout-coach skill）

## Anti-Patterns

1. **不要过度解读关联** — 个人级别的数据量小（30天≈30个样本），任何关联都是观察性的，不代表因果。始终标注"D级证据(个人观察)"。
2. **不要隐藏数据缺失** — 如果某个数据源覆盖率低，必须在回复中明确指出，不要用有限数据做过度推断。
3. **不要混淆数据时效** — 3个月前的体检报告和昨天的 Garmin 数据不在同一时效维度，应分别标注。
4. **不要忽略基因数据的上下文** — 基因数据是永久有效的，但解读需结合当前状态（如基因提示高血压风险 + 当前血压正常 = 需持续监测，非立即干预）。

## Evidence & Caveats

| 组件 | 证据等级 | 说明 |
|------|----------|------|
| 数据完整性报告 | N/A | 纯描述性统计，无推断 |
| 综合健康画像 | N/A | 数据聚合展示，无评判 |
| 跨模态关联 | D级 | 个人级别的简单统计关联，样本量小 |
| 饮食-HRV关联 | D级 | 文献中有支持但非个人验证 |
| 睡眠-活动关联 | C级 | 群体研究支持，个人变异大 |

**限制说明：**
- 关联分析需至少 14 天数据才有意义
- 饮食数据质量严重依赖用户记录频率
- 基因数据解读需结合最新体检结果
- 所有关联均为统计观察，不构成医学建议

## Response Rules

1. 所有回复使用中文
2. 综合画像应简洁，突出关键指标和异常项
3. 数据新鲜度用自然语言描述（"今天"、"3天前"、"21天前"）
4. 关联发现必须附带证据等级和样本量
5. 数据缺失时给出具体、可操作的改善建议
6. 不对缺失数据做假设填充
