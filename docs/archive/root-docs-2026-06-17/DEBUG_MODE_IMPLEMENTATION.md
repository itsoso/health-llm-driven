# Debug 模式实现文档

## 功能概述

为运动前智能建议和运动后复盘添加 debug 模式，可视化展示 AI 的决策过程和数据来源。

## 实现内容

### 1. 运动前指导 Debug 模式

**服务**: `PreWorkoutGuidanceService`
**API**: `POST /api/v1/workout/pre-workout-guidance?debug=true`

#### Debug 信息结构

```json
{
  "success": true,
  "workout_type": "RUNNING",
  "training_objective": "...",
  "heart_rate_zones": {...},
  "warm_up": [...],
  "key_reminders": [...],
  "course_insights": [...],
  
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
        "goal_type": "EXERCISE",
        "target_value": 5.0,
        "target_unit": "分钟/公里"
      },
      "recent_health": {
        "sleep_score": 85,
        "sleep_hours": 7.5,
        "stress_level": 35,
        "resting_hr": 48,
        "hrv": 65,
        "body_battery": 85,
        "recent_activity": 5
      },
      "heart_rate_zones": {
        "zone1_recovery": [113, 126],
        "zone2_fat_burn": [126, 139],
        "zone3_aerobic": [139, 152],
        "zone4_threshold": [152, 165],
        "zone5_max": [165, 179],
        "max_heart_rate": 179,
        "resting_heart_rate": 48
      },
      "knowledge_query": "进行RUNNING训练前需要注意什么？提升5公里配速",
      "knowledge_results": [
        {
          "content": "跑步训练前应进行充分的热身，包括动态拉伸和慢跑...",
          "source": "张展晖-运动科学基础",
          "score": 0.89
        }
      ]
    },
    "reasoning": [
      "✅ 用户资料：35岁，男，体重70kg",
      "🎯 自动选择活跃目标：提升5公里配速",
      "📊 最近健康状态：睡眠评分85, 静息心率48bpm, HRV 65ms, 身体电量85",
      "💓 基于年龄35岁和静息心率48bpm计算5个心率区间",
      "   - 最大心率: 179bpm",
      "   - 建议训练区间(Zone 2): 126-139bpm",
      "🏃 根据目标推断运动类型：RUNNING",
      "📚 知识库查询：进行RUNNING训练前需要注意什么？提升5公里配速",
      "📖 从知识库检索到3条相关内容",
      "✅ 生成完成，包含以下内容：",
      "   - 热身建议：5条",
      "   - 关键提醒：6条",
      "   - 课程要点：3条"
    ]
  }
}
```

### 2. 运动后分析 Debug 模式

**服务**: `PostWorkoutAnalysisService`
**API**: `POST /api/v1/workout/post-workout-analysis/{workout_id}?debug=true`

#### Debug 信息结构

```json
{
  "success": true,
  "workout_summary": {...},
  "hr_analysis": {...},
  "intensity_assessment": {...},
  "recovery_tips": [...],
  "improvement_tips": [...],
  
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
        "workout_date": "2026-01-21",
        "duration_seconds": 2400,
        "distance_meters": 5000,
        "avg_heart_rate": 145,
        "max_heart_rate": 168,
        "avg_pace_seconds_per_km": 480,
        "calories": 350,
        "training_effect_aerobic": 3.2,
        "training_effect_anaerobic": 1.5
      },
      "user_profile": {
        "age": 35,
        "weight": 70,
        "fitness_level": "中等"
      },
      "heart_rate_zones": {
        "zone1_recovery": [113, 126],
        "zone2_fat_burn": [126, 139],
        "zone3_aerobic": [139, 152],
        "zone4_threshold": [152, 165],
        "zone5_max": [165, 179]
      },
      "hr_zone_distribution": {
        "zone1_seconds": 120,
        "zone2_seconds": 600,
        "zone3_seconds": 1200,
        "zone4_seconds": 420,
        "zone5_seconds": 60
      },
      "knowledge_query": "running训练后如何恢复？心率主要在有氧区间",
      "knowledge_results": [...]
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
      "   - 无氧训练效果1.5 (适中)",
      "📚 知识库查询：running训练后如何恢复？",
      "📖 检索到3条恢复建议",
      "✅ 生成完成：",
      "   - 恢复建议：5条",
      "   - 改进建议：4条",
      "   - 目标进度：配速较目标慢20秒/公里"
    ]
  }
}
```

## 前端展示

### 1. Debug 开关

在运动指导页面添加 debug 模式开关：

```tsx
const [debugMode, setDebugMode] = useState(false);

<Toggle
  label="Debug 模式"
  checked={debugMode}
  onChange={setDebugMode}
/>
```

### 2. Debug 信息面板

```tsx
{guidance.debug && (
  <DebugPanel>
    <h3>🔍 决策过程</h3>
    
    {/* 步骤展示 */}
    <Steps>
      {guidance.debug.steps.map((step, index) => (
        <Step key={index} completed>{step}</Step>
      ))}
    </Steps>
    
    {/* 数据来源 */}
    <Section title="📊 数据来源">
      <DataSourceCard data={guidance.debug.data_sources} />
    </Section>
    
    {/* 推理过程 */}
    <Section title="🧠 推理过程">
      {guidance.debug.reasoning.map((reason, index) => (
        <ReasoningItem key={index}>{reason}</ReasoningItem>
      ))}
    </Section>
  </DebugPanel>
)}
```

## 使用场景

### 1. 开发调试
- 观察 AI 使用了哪些数据源
- 验证知识库检索是否准确
- 调试心率区间计算逻辑

### 2. 用户信心
- 展示建议的科学依据
- 让用户了解系统如何分析他们的数据
- 增强对 AI 建议的信任

### 3. 参数调优
- 观察不同参数对结果的影响
- 优化知识库检索策略
- 改进心率区间计算公式

## 实现文件

1. `backend/app/services/pre_workout_guidance.py` - 运动前指导 debug
2. `backend/app/services/post_workout_analysis.py` - 运动后分析 debug
3. `backend/app/api/workout.py` - API 接口更新
4. `frontend/src/components/DebugPanel.tsx` - Debug 面板组件
5. `frontend/src/app/workout-guidance/page.tsx` - 前端页面更新

## 部署计划

1. 后端服务更新
2. API 接口测试
3. 前端组件开发
4. 集成测试
5. 生产环境部署
