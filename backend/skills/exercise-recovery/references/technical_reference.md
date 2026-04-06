# 运动恢复技术参考文档

## 1. TRIMP（训练冲量）计算

### 1.1 原始 TRIMP 公式（Banister 1991）

```
TRIMP = Duration(min) x HRr x 0.64 x e^(1.92 x HRr)   (男性)
TRIMP = Duration(min) x HRr x 0.86 x e^(1.67 x HRr)   (女性)
```

其中 HRr（心率储备比例）:
```
HRr = (HR_exercise - HR_rest) / (HR_max - HR_rest)
```

### 1.2 简化 TRIMP（本系统采用）

由于逐分钟心率数据不总是可用，系统使用简化版：

```
TRIMP = Duration(min) x Intensity_Coefficient
```

强度系数基于平均心率与最大心率的比值：

| HR%max 区间 | 系数 | 对应心率区间 |
|------------|------|------------|
| < 60%      | 1.0  | Zone 1（恢复区）|
| 60-70%     | 1.5  | Zone 2（燃脂区）|
| 70-80%     | 2.0  | Zone 3（有氧区）|
| 80-90%     | 3.0  | Zone 4（阈值区）|
| 90-100%    | 4.0  | Zone 5（极限区）|

示例：60 分钟跑步，平均心率 150bpm，最大心率 190bpm
- HR%max = 150/190 = 78.9% -> Zone 3 系数 2.0
- TRIMP = 60 x 2.0 = 120

### 1.3 Garmin Training Load 对照

Garmin 设备本身提供 `training_load` 字段（EPOC 基础算法）。当 Garmin 值可用时：
- 优先使用 Garmin training_load 作为当日 TRIMP
- 回退使用简化 TRIMP 公式

## 2. ACWR（急性:慢性负荷比）

### 2.1 滚动平均法（Rolling Average）

```
Acute Load  = sum(TRIMP_day[-7:]) / 7    # 最近 7 天平均
Chronic Load = sum(TRIMP_day[-28:]) / 28  # 最近 28 天平均
ACWR = Acute Load / Chronic Load
```

### 2.2 指数加权移动平均法（EWMA）

更精确的方法，对近期数据赋予更高权重：

```
lambda_a = 2 / (7 + 1)    # 急性衰减系数
lambda_c = 2 / (28 + 1)   # 慢性衰减系数

EWMA_acute(t) = TRIMP(t) x lambda_a + (1 - lambda_a) x EWMA_acute(t-1)
EWMA_chronic(t) = TRIMP(t) x lambda_c + (1 - lambda_c) x EWMA_chronic(t-1)

ACWR = EWMA_acute / EWMA_chronic
```

**本系统使用滚动平均法**，因为更直观且对数据缺失更鲁棒。

### 2.3 ACWR 阈值解读

| ACWR 范围 | 分类 | 含义 | 建议 |
|-----------|------|------|------|
| < 0.8     | 训练不足 | 慢性负荷下降 | 可以安全增加训练量 |
| 0.8 - 1.0 | 偏低 | 训练略低于平常 | 可适当提高 |
| 1.0 - 1.3 | 最佳 | 训练负荷合理 | 保持当前水平 |
| 1.3 - 1.5 | 警告 | 负荷增长过快 | 控制增量 |
| > 1.5     | 危险 | 过度训练风险高 | 减量或休息 |

## 3. 恢复就绪度（Recovery Readiness）

### 3.1 综合评分公式

```
Recovery Score = w_hrv x HRV_score + w_sleep x Sleep_score
              + w_stress x Stress_score + w_bb x BodyBattery_score
```

权重分配：
- w_hrv = 0.30（HRV 对恢复最敏感）
- w_sleep = 0.30（睡眠是恢复的基础）
- w_stress = 0.20（压力影响自主神经系统）
- w_bb = 0.20（身体电量综合反映恢复状态）

### 3.2 各分项评分计算

**HRV 评分（0-100）:**
```
if hrv_7day_avg 可用:
    baseline = hrv_7day_avg
    deviation = (hrv_today - baseline) / baseline
    hrv_score = 50 + deviation x 100   # 高于基线加分，低于减分
    hrv_score = clamp(hrv_score, 0, 100)
else:
    # 无基线数据，使用绝对值映射
    hrv_score = min(hrv_today / 80 x 100, 100)  # 80ms 视为满分
```

**睡眠评分（0-100）:**
- 直接使用 Garmin sleep_score（0-100）
- 如无 Garmin 数据，基于睡眠时长：<6h=30, 6-7h=50, 7-8h=75, 8-9h=90, >9h=80

**压力评分（0-100）:**
```
stress_score = 100 - stress_level  # Garmin stress 0-100，越低越好
```

**身体电量评分（0-100）:**
```
# 使用当前电量或最高充电值
body_battery_score = body_battery_current or body_battery_most_charged
```

### 3.3 就绪度等级

| 分数范围 | 等级 | 含义 |
|---------|------|------|
| 75-100  | high | 完全恢复，可进行高强度训练 |
| 50-74   | moderate | 部分恢复，适合中等强度 |
| 25-49   | low  | 恢复不足，建议轻度活动 |
| 0-24    | very_low | 严重疲劳，建议完全休息 |

## 4. 训练建议矩阵

基于恢复就绪度和 ACWR 的二维矩阵：

| ACWR \ 就绪度 | high (>=75) | moderate (50-74) | low (<50) |
|---------------|-------------|------------------|-----------|
| < 0.8（不足）  | hard        | moderate         | light     |
| 0.8-1.3（最佳）| hard        | moderate         | light     |
| 1.3-1.5（警告）| moderate    | light            | rest      |
| > 1.5（危险）  | light       | rest             | rest      |

### 建议强度说明

| 级别 | 目标心率区 | 建议时长 | 推荐类型 |
|------|----------|---------|---------|
| rest | 不训练    | 0       | 完全休息、拉伸 |
| light | Zone 1-2 | 30-45min | 散步、瑜伽、轻度游泳 |
| moderate | Zone 2-3 | 45-75min | 有氧跑、骑行、游泳 |
| hard | Zone 3-4 | 60-90min | 间歇跑、力量训练、HIIT |
| peak | Zone 4-5 | 45-75min | 比赛配速训练、全力冲刺 |

## 5. 周期化建议

### 微周期（1 周）
- 2-3 天训练 + 1 天恢复为一个循环
- 避免连续 3 天以上高强度训练
- 周训练负荷增长不超过 10%（"10% 规则"）

### 中周期（4 周）
- 3 周递增 + 1 周减量（3:1 模式）
- 减量周训练量降低 40-60%

### 超量恢复
- 训练后 24-72 小时为超量恢复窗口
- 高强度训练建议间隔 48 小时以上
- HRV 恢复到基线水平作为下次高强度训练的信号
