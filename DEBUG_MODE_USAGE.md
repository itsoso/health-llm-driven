# Debug 模式使用指南

## 功能说明

Debug 模式可以展示 AI 运动指导的完整决策过程，包括：
- 使用了哪些数据源
- 每一步的决策逻辑
- 知识库检索的内容
- 最终建议的生成依据

## API 使用

### 1. 运动前指导 Debug 模式

```bash
# 普通模式
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"

# Debug 模式
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

**响应示例（Debug 模式）：**

```json
{
  "success": true,
  "workout_type": "RUNNING",
  "training_objective": "今日建议进行RUNNING训练，保持适当强度，注意心率控制。",
  "heart_rate_zones": {
    "zone1_recovery": [113, 126],
    "zone2_fat_burn": [126, 139],
    "zone3_aerobic": [139, 152],
    "zone4_threshold": [152, 165],
    "zone5_max": [165, 179],
    "max_heart_rate": 179,
    "resting_heart_rate": 48
  },
  "warm_up": [
    "动态拉伸 5-10 分钟，激活肌肉",
    "从低强度开始，逐渐提升心率",
    "慢跑 5 分钟热身"
  ],
  "key_reminders": [
    "💓 保持心率在 126-139 bpm（有氧区间）",
    "✨ 睡眠充足，状态良好，可以正常训练",
    "💧 运动前 30 分钟补充 200-300ml 水"
  ],
  "course_insights": [
    "跑步训练前应进行充分的热身...",
    "控制心率在有氧区间可以提升耐力...",
    "注意呼吸节奏，避免过度换气..."
  ],
  
  "debug": {
    "steps": [
      "1. 获取用户基本信息",
      "2. 获取用户运动目标",
      "3. 获取最近7天Garmin健康数据",
      "4. 计算个性化心率区间",
      "5. 确定运动类型",
      "6. 从张展晖课程知识库检索相关建议",
      "7. 生成个性化运动指导"
    ],
    "data_sources": {
      "user_profile": {
        "age": 35,
        "gender": "男",
        "weight": 70,
        "height": 175,
        "fitness_level": "中等"
      },
      "goal": {
        "title": "提升5公里配速",
        "description": "在3个月内将5公里配速提升到5分钟/公里",
        "goal_type": "EXERCISE"
      },
      "recent_health": {
        "sleep_score": 85,
        "sleep_hours": 7.5,
        "resting_hr": 48,
        "hrv": 65,
        "body_battery": 85
      },
      "heart_rate_zones": { ... },
      "knowledge_query": "进行RUNNING训练前需要注意什么？提升5公里配速",
      "knowledge_results": [
        {
          "content": "跑步训练前应进行充分的热身...",
          "source": "张展晖-运动科学基础",
          "score": 0.89
        }
      ]
    },
    "reasoning": [
      "✅ 用户资料：35岁，男，体重70kg",
      "🎯 自动选择活跃目标：提升5公里配速",
      "📊 最近健康状态：睡眠评分85, 静息心率48bpm, HRV 65ms",
      "💓 基于年龄35岁和静息心率48bpm计算5个心率区间",
      "   - 最大心率: 179bpm",
      "   - 建议训练区间(Zone 2): 126-139bpm",
      "🏃 根据目标推断运动类型：RUNNING",
      "📚 知识库查询：进行RUNNING训练前需要注意什么？",
      "📖 从知识库检索到3条相关内容",
      "✅ 生成完成，包含热身建议5条、关键提醒6条、课程要点3条"
    ]
  }
}
```

### 2. 运动后分析 Debug 模式

```bash
# 普通模式
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/post-workout-analysis/123" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Debug 模式
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/post-workout-analysis/123?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Debug 模式 + 强制重新生成
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/post-workout-analysis/123?debug=true&force_regenerate=true" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例（Debug 模式）：**

```json
{
  "success": true,
  "workout_summary": {
    "workout_type": "running",
    "duration": "40分钟",
    "distance": "5.0公里",
    "avg_pace": "8'00\"/km"
  },
  "hr_analysis": {
    "has_hr_data": true,
    "avg_hr": 145,
    "max_hr": 168,
    "primary_zone": "Zone 3 (有氧)"
  },
  "intensity_assessment": {
    "intensity_level": "中等强度有氧训练",
    "aerobic_effect": 3.2,
    "anaerobic_effect": 1.5
  },
  "recovery_tips": [
    "运动后30分钟内补充蛋白质和碳水化合物",
    "进行10-15分钟静态拉伸",
    "保证充足睡眠，促进恢复"
  ],
  "improvement_tips": [
    "下次训练可以尝试间歇跑，提升速度",
    "增加Zone 2训练比例，提升有氧基础",
    "注意配速稳定性，避免忽快忽慢"
  ],
  
  "debug": {
    "steps": [
      "1. 获取运动记录详情",
      "2. 获取用户基本信息",
      "3. 计算心率区间基准",
      "4. 分析心率区间分布",
      "5. 评估训练强度",
      "6. 从知识库检索恢复建议",
      "7. 生成个性化恢复和改进建议",
      "8. 对比目标进度"
    ],
    "data_sources": {
      "workout": {
        "workout_type": "running",
        "duration_seconds": 2400,
        "distance_meters": 5000,
        "avg_heart_rate": 145,
        "max_heart_rate": 168,
        "training_effect_aerobic": 3.2
      },
      "user_profile": {
        "age": 35,
        "weight": 70,
        "fitness_level": "中等"
      },
      "heart_rate_zones": { ... },
      "hr_zone_distribution": {
        "zone1_seconds": 120,
        "zone2_seconds": 600,
        "zone3_seconds": 1200,
        "zone4_seconds": 420,
        "zone5_seconds": 60
      }
    },
    "reasoning": [
      "✅ 运动记录：跑步，5.0公里，用时40分钟",
      "✅ 用户资料：35岁，体重70kg，中等健身水平",
      "💓 计算心率区间基准：最大心率179bpm",
      "📊 心率分布分析：",
      "   - Zone 1 (恢复): 5% (120秒)",
      "   - Zone 2 (燃脂): 25% (600秒)",
      "   - Zone 3 (有氧): 50% (1200秒) ✅ 主要区间",
      "   - Zone 4 (乳酸阈): 17.5% (420秒)",
      "   - Zone 5 (最大): 2.5% (60秒)",
      "💪 训练强度评估：中等强度有氧训练",
      "   - 平均心率145bpm (Zone 3)",
      "   - 有氧训练效果3.2 (良好)",
      "📚 知识库查询：running训练后如何恢复？",
      "📖 检索到3条恢复建议",
      "✅ 生成完成：恢复建议5条、改进建议4条"
    ]
  }
}
```

## 使用场景

### 1. 开发调试
```bash
# 测试知识库检索是否准确
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true&workout_type=RUNNING" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.debug.data_sources.knowledge_results'

# 验证心率区间计算
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.debug.data_sources.heart_rate_zones'
```

### 2. 参数调优
```bash
# 观察不同健康状态下的建议差异
# 比较睡眠充足 vs 睡眠不足时的建议

# 观察不同运动类型的知识库检索
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true&workout_type=CARDIO" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.debug.reasoning'
```

### 3. 用户信心增强
在前端展示 debug 信息，让用户了解：
- AI 使用了他们的哪些数据
- 建议是如何生成的
- 科学依据来自哪里

## 前端集成示例

```typescript
// 获取运动前指导（带 debug）
const getPreWorkoutGuidance = async (debug: boolean = false) => {
  const response = await fetch(
    `${API_BASE}/workout/pre-workout-guidance?debug=${debug}`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );
  return response.json();
};

// 展示 debug 信息
{guidance.debug && (
  <DebugPanel>
    <h3>🔍 AI 决策过程</h3>
    
    {/* 步骤 */}
    <div className="steps">
      {guidance.debug.steps.map((step, i) => (
        <div key={i} className="step">✓ {step}</div>
      ))}
    </div>
    
    {/* 推理过程 */}
    <div className="reasoning">
      {guidance.debug.reasoning.map((reason, i) => (
        <div key={i} className="reason">{reason}</div>
      ))}
    </div>
    
    {/* 数据来源 */}
    <details>
      <summary>查看详细数据来源</summary>
      <pre>{JSON.stringify(guidance.debug.data_sources, null, 2)}</pre>
    </details>
  </DebugPanel>
)}
```

## 注意事项

1. **性能影响**：Debug 模式会返回更多数据，响应体积会增大约 2-3 倍
2. **缓存策略**：Debug 模式会跳过缓存，始终生成新的分析
3. **生产环境**：建议仅在开发/测试环境或管理员账户使用 debug 模式
4. **隐私保护**：Debug 信息包含用户详细数据，注意前端展示时的隐私保护

## 测试命令

```bash
# 测试运动前指导 debug
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" | jq '.debug.reasoning'

# 测试运动后分析 debug
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/post-workout-analysis/WORKOUT_ID?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" | jq '.debug.reasoning'
```

## 相关文档

- [DEBUG_MODE_IMPLEMENTATION.md](./DEBUG_MODE_IMPLEMENTATION.md) - 实现文档
- [WORKOUT_GUIDANCE_SUMMARY.md](./WORKOUT_GUIDANCE_SUMMARY.md) - 运动指导功能总结
