# 环境因素智能提醒功能说明

## ✅ 已完成

### 1. 功能概述
在运动前指导中集成了环境因素（天气 + 空气质量）智能提醒功能。

### 2. 核心功能

#### 2.1 自动检测环境因素
- **天气状况**：温度、湿度、降雨、雾霾、风速等
- **空气质量**：AQI、PM2.5、PM10 等污染物指标
- **户外运动适宜度**：0-100 分评分系统

#### 2.2 智能提醒规则

| 条件 | 提醒内容 | 建议 |
|------|---------|------|
| AQI > 150 | ⚠️ 空气质量{等级}（AQI {值}） | 强烈建议室内运动 |
| AQI > 100 | ⚠️ 空气质量{等级}（AQI {值}） | 建议减少户外运动时间 |
| 雾霾天气 | ⚠️ 天气状况不佳（雾霾） | 建议室内运动 |
| 温度 < 5°C | ⚠️ 温度过低 | 室内运动或做好保暖 |
| 温度 > 35°C | ⚠️ 温度过高 | 空调环境下运动 |
| 降雨/降雪 | ⚠️ 天气状况不佳 | 建议室内运动 |
| 大风 > 40km/h | ⚠️ 风速过大 | 不宜户外运动 |

#### 2.3 个性化建议
根据用户慢性病自动生成针对性建议：

- **鼻炎患者**：
  - AQI > 100：外出建议佩戴口罩，回家后及时洗鼻
  - AQI > 150：尽量减少外出，增加洗鼻频次
  - 天气寒冷：注意保暖防止鼻炎加重
  - 空气干燥：使用加湿器，保持鼻腔湿润

- **哮喘患者**：
  - AQI > 100：避免户外活动，随身携带急救药物

- **心血管疾病**：
  - 极端温度：避免剧烈运动

- **关节炎/风湿**：
  - 湿度 > 80%：注意关节保暖

### 3. 数据来源

#### 3.1 空气质量数据
- **主要来源**：aqicn.org（官方环保厅监测站数据）
- **备用来源**：Open-Meteo（全球空气质量模型）
- **更新频率**：30 分钟缓存

#### 3.2 天气数据
- **来源**：Open-Meteo（免费，无需 API Key）
- **数据项**：温度、体感温度、湿度、天气状况、风速、气压
- **更新频率**：30 分钟缓存

### 4. API 响应示例

#### 4.1 运动前指导响应（新增字段）

```json
{
  "success": true,
  "workout_type": "RUNNING",
  "environment": {
    "weather": {
      "temperature": 8,
      "feels_like": 5,
      "humidity": 65,
      "description": "多云",
      "summary": "多云，8°C，湿度65%"
    },
    "air_quality": {
      "aqi": 125,
      "level": "moderate",
      "description": "轻度污染",
      "pm25": 85
    },
    "outdoor_suitable": false,
    "outdoor_score": 60,
    "status": "moderate",
    "recommended_activities": ["室内健身", "游泳", "瑜伽"],
    "advices": [
      "空气质量一般，敏感人群应减少户外运动",
      "注意防寒保暖",
      "运动时注意散热"
    ]
  },
  "key_reminders": [
    "⚠️ 空气质量轻度污染（AQI 125），建议减少户外运动时间",
    "⚠️ 空气质量影响呼吸，鼻炎患者需特别注意防护",
    "💓 保持心率在 126-139 bpm（有氧区间）",
    "💧 运动前 30 分钟补充 200-300ml 水"
  ]
}
```

#### 4.2 Debug 模式新增信息

```json
{
  "debug": {
    "steps": [
      "1. 获取用户基本信息",
      "2. 获取用户运动目标",
      "3. 获取最近7天Garmin健康数据",
      "4. 计算个性化心率区间",
      "5. 检测环境因素（天气和空气质量）",
      "6. 确定运动类型",
      "7. 从张展晖课程知识库检索相关建议",
      "8. 生成个性化运动指导"
    ],
    "reasoning": [
      "✅ 用户资料：41岁, male, 体重76.0kg",
      "🎯 使用指定目标：每日运动30分钟",
      "📊 最近健康状态：睡眠评分87, 静息心率46bpm",
      "ℹ️ 当前天气：多云，8°C",
      "⚠️ 空气质量：轻度污染（AQI 125）",
      "⚠️ 空气质量差，不适合户外运动",
      "⚠️ 户外运动适宜度：60/100（不推荐户外）"
    ],
    "data_sources": {
      "environment": {
        "city": "杭州",
        "weather": {
          "available": true,
          "temperature": 8,
          "humidity": 65,
          "weather": "多云"
        },
        "air_quality": {
          "available": true,
          "aqi": 125,
          "level": "moderate",
          "description": "轻度污染",
          "pm25": 85
        },
        "outdoor_suitable": false,
        "score": 60
      }
    }
  }
}
```

### 5. 使用方法

#### 5.1 前端调用
```typescript
// 获取运动前指导（自动包含环境因素）
const guidance = await workoutGuidanceApi.getPreWorkoutGuidance(
  goalId,
  workoutType,
  debug  // 开启 debug 可查看环境数据来源
);

// 显示环境警告
if (guidance.environment && !guidance.environment.outdoor_suitable) {
  showWarning(guidance.environment.advices);
}
```

#### 5.2 配置环境变量（可选）
```bash
# 空气质量 API Token（可选，不配置则使用 demo token）
AQICN_API_TOKEN=your_token_here

# 注册地址：https://aqicn.org/data-platform/token/
```

### 6. 技术实现

#### 6.1 架构设计
```
PreWorkoutGuidanceService
  ├── 获取用户信息
  ├── 获取健康数据
  ├── 计算心率区间
  ├── 检测环境因素 ← 新增
  │   ├── WeatherService（天气）
  │   ├── AirQualityService（空气质量）
  │   └── EnvironmentAdvisor（综合建议）
  ├── 检索知识库
  └── 生成指导
```

#### 6.2 异步处理
- 使用 `async/await` 异步获取环境数据
- 失败时不阻塞主流程，使用默认值
- 30 分钟缓存，减少 API 调用

#### 6.3 错误处理
```python
try:
    environment_data = await environment_advisor.get_comprehensive_advice(...)
except Exception as e:
    logger.error(f"获取环境数据失败: {e}")
    # 继续生成指导，不影响主流程
```

### 7. 测试验证

#### 7.1 测试步骤
1. 打开运动前指导页面：https://health.westwetlandtech.com/workout-guidance
2. 选择运动目标和类型
3. 开启 Debug 模式
4. 点击"获取运动前指导"
5. 查看 Debug 面板中的"检测环境因素"步骤

#### 7.2 预期结果
- ✅ 显示当前天气和空气质量
- ✅ 根据 AQI 显示相应警告
- ✅ 雾霾天气提示室内运动
- ✅ 鼻炎患者显示针对性建议
- ✅ Debug 面板显示环境数据来源

### 8. 后续优化方向

1. **前端 UI 优化**
   - 添加天气和空气质量卡片
   - 可视化户外运动适宜度评分
   - 环境警告高亮显示

2. **数据精度提升**
   - 支持用户自定义城市
   - 支持 GPS 定位获取精确位置
   - 增加更多天气指标（紫外线、花粉等）

3. **智能推荐**
   - 根据环境自动推荐室内/户外运动
   - 推荐最佳运动时间段
   - 结合天气预报规划未来运动

4. **通知提醒**
   - 空气质量突变时推送通知
   - 适合运动的天气窗口提醒

---

## 📝 更新日志

### 2026-01-21
- ✅ 集成环境服务（天气 + 空气质量）
- ✅ 实现智能提醒规则
- ✅ 支持个性化建议（鼻炎、哮喘等）
- ✅ Debug 模式显示环境数据
- ✅ 部署到生产环境

---

## 🔗 相关文档

- [环境服务实现](backend/app/services/environment/)
- [运动前指导服务](backend/app/services/pre_workout_guidance.py)
- [API 文档](backend/app/api/workout.py)
