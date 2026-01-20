# 张展晖课程集成快速开始

> 将张展晖的运动科学课程集成到健康管理系统，实现科学的目标设定和运动指导

**完成时间**: 2026-01-20  
**状态**: ✅ 知识库优化完成，可以开始上传课程

---

## 🎯 目标

将张展晖的得到课程加入到知识库中，用于：

1. **目标设定** - 用户创建减肥或跑步目标时，基于课程内容科学指导
2. **心率区间计算** - 根据年龄和静息心率计算个性化训练区间
3. **运动指导** - 运动前推送训练建议，运动后个性化分析
4. **进度评估** - 定期生成报告，调整训练计划

---

## ✅ 已完成的工作

### 1. 增强版知识库系统

**核心改进**:
- ✅ 保留 Markdown 标题层级和面包屑导航
- ✅ 更大的分块大小（1800-2000 字符），适配完整知识点
- ✅ 丰富的元数据（作者、难度、目标人群、关键概念）
- ✅ 智能分类识别（9种运动科学分类）
- ✅ 关键概念自动提取

**技术文档**:
- `backend/KNOWLEDGE_BASE_ENHANCED.md` - 详细技术说明
- `backend/KNOWLEDGE_BASE_OPTIMIZATION_SUMMARY.md` - 优化总结

### 2. 课程上传工具

**API 端点**: `POST /knowledge/documents/course`

**上传脚本**: `backend/scripts/upload_zhang_zhanhui_course.py`

**使用指南**: `backend/UPLOAD_GUIDE.md`

---

## 🚀 快速开始

### 第一步：上传张展晖课程

#### 1. 启动后端服务

```bash
cd backend
source venv/bin/activate
./start-server.sh
```

#### 2. 获取管理员 Token

访问 http://localhost:8000/docs，使用 `/auth/login` 接口登录，复制 `access_token`

或使用 curl:
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your_password"}'
```

#### 3. 上传课程文件

**方法 A: 批量上传目录（推荐）**

```bash
cd backend

python scripts/upload_zhang_zhanhui_course.py \
  --dir /path/to/zhang_zhanhui_courses \
  --token "YOUR_ACCESS_TOKEN"
```

**方法 B: 上传单个文件**

```bash
python scripts/upload_zhang_zhanhui_course.py \
  --file /path/to/01_心肺功能是一切基础.md \
  --token "YOUR_ACCESS_TOKEN"
```

#### 4. 验证上传

```bash
# 查看知识库统计
curl http://localhost:8000/knowledge/stats \
  -H "Authorization: Bearer YOUR_TOKEN"

# 测试搜索
python scripts/upload_zhang_zhanhui_course.py --test --token YOUR_TOKEN
```

**预期输出**:
```json
{
  "total_documents": 45,
  "sources": {
    "zhang_zhanhui": 45
  },
  "categories": {
    "cardio_training": 15,
    "strength_training": 10,
    "nutrition": 8
  }
}
```

---

### 第二步：测试知识检索

#### 测试基础搜索

```bash
curl -X POST "http://localhost:8000/knowledge/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何根据心率进行有氧训练",
    "n_results": 3,
    "source": "zhang_zhanhui"
  }'
```

#### 测试 RAG 问答

```bash
curl -X POST "http://localhost:8000/knowledge/ask" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "我35岁，静息心率60，想减脂，应该在什么心率区间训练？",
    "category": "cardio_training",
    "include_health_data": false
  }'
```

---

### 第三步：实现业务功能

现在可以开始实现基于张展晖课程的业务功能了！

#### 功能 1: 目标设定时的智能引导

**场景**: 用户创建"减肥目标"时，系统自动生成科学的训练计划

**实现要点**:
```python
# backend/app/services/goal_guidance.py

from app.services.knowledge.rag_pipeline import rag_pipeline
from app.services.digital_twin import DigitalTwinService

async def generate_training_plan_for_goal(
    db: Session,
    user_id: int,
    goal_type: str,  # "weight_loss" 或 "running_endurance"
    target_value: float
):
    # 1. 获取用户数字孪生数据
    twin = DigitalTwinService(db, user_id)
    hr_zones = twin.calculate_target_heart_rate_zones()
    
    # 2. 从知识库检索相关训练方法
    query = f"如何通过{goal_type}训练达到目标"
    knowledge = rag_pipeline.retrieve_relevant_knowledge(
        query=query,
        category="cardio_training",
        n_results=5
    )
    
    # 3. 生成个性化训练计划
    plan = rag_pipeline.generate_with_knowledge(
        user_query=f"为{goal_type}目标生成训练计划",
        user_context={
            "age": twin.profile.age,
            "resting_hr": hr_zones["resting_heart_rate"],
            "heart_rate_zones": hr_zones,
            "goal": goal_type,
            "target": target_value
        },
        category="goal_setting"
    )
    
    return {
        "heart_rate_zones": hr_zones,
        "training_plan": plan,
        "knowledge_references": knowledge
    }
```

#### 功能 2: 运动前的实时指导

**场景**: 用户准备运动时，推送今日训练建议

**实现要点**:
```python
# backend/app/services/workout_guidance.py

async def generate_pre_workout_guidance(
    db: Session,
    user_id: int
):
    # 1. 检测恢复状态
    twin = DigitalTwinService(db, user_id)
    latest_data = get_latest_garmin_data(db, user_id)
    
    recovery_score = calculate_recovery_score(
        hrv=latest_data.hrv,
        body_battery=latest_data.body_battery,
        sleep_score=latest_data.sleep_score
    )
    
    # 2. 确定今日训练类型
    training_type = determine_training_type(recovery_score)
    
    # 3. 从知识库检索训练方法
    guidance = rag_pipeline.generate_with_knowledge(
        user_query=f"今日进行{training_type}训练的要点",
        user_context={
            "recovery_score": recovery_score,
            "heart_rate_zones": twin.calculate_target_heart_rate_zones()
        },
        category="cardio_training"
    )
    
    return guidance
```

#### 功能 3: 运动后的个性化分析

**场景**: 运动结束后，深度分析运动数据

**实现要点**:
```python
# backend/app/services/workout_analysis_enhanced.py

async def analyze_workout_with_knowledge(
    db: Session,
    user_id: int,
    workout_id: int
):
    # 1. 获取运动数据
    workout = get_workout_record(db, workout_id)
    hr_distribution = calculate_hr_zone_distribution(workout)
    
    # 2. 从知识库检索评估标准
    analysis = rag_pipeline.generate_with_knowledge(
        user_query=f"评估这次{workout.workout_type}训练的质量",
        user_context={
            "hr_distribution": hr_distribution,
            "duration": workout.duration_minutes,
            "avg_hr": workout.avg_heart_rate
        },
        category="cardio_training"
    )
    
    # 3. 生成改进建议
    recommendations = rag_pipeline.generate_with_knowledge(
        user_query="如何改进下次训练",
        user_context=analysis,
        category="performance"
    )
    
    return {
        "analysis": analysis,
        "recommendations": recommendations
    }
```

---

## 📊 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户交互层                                 │
│  (创建目标 / 准备运动 / 运动结束 / 查看报告)                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        业务逻辑层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 目标设定引导  │  │ 运动前指导    │  │ 运动后分析    │          │
│  │ GoalGuidance │  │WorkoutGuidance│  │WorkoutAnalysis│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        知识增强层 (RAG)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  RAG Pipeline                                             │  │
│  │  • 检索相关知识                                            │  │
│  │  • 结合用户画像                                            │  │
│  │  • 生成个性化建议                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        知识库层                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  张展晖课程知识库 (Vector Store)                           │  │
│  │  • 心率区间训练法                                          │  │
│  │  • 五区心率训练                                            │  │
│  │  • 减脂训练方法                                            │  │
│  │  • 力量训练指导                                            │  │
│  │  • 营养补给策略                                            │  │
│  │  • 恢复与预防                                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        数据层                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ 用户画像      │  │ Garmin 数据   │  │ 目标进度      │          │
│  │ UserProfile  │  │ GarminData   │  │ GoalProgress │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎓 知识库内容示例

上传后的知识库结构：

```
张展晖课程知识库
├── 01_心肺功能是一切基础
│   ├── 心肺功能的重要性
│   ├── 如何评估心肺功能
│   └── 提升心肺功能的方法
│
├── 02_如何科学有效地提升心肺能力
│   ├── 心率区间训练法
│   │   ├── 为什么要监测心率
│   │   ├── 最大心率计算
│   │   └── 储备心率法（Karvonen公式）
│   ├── 五区心率训练法
│   │   ├── Zone 1 - 恢复区（50-60%）
│   │   ├── Zone 2 - 有氧基础区（60-70%）⭐
│   │   ├── Zone 3 - 有氧耐力区（70-80%）
│   │   ├── Zone 4 - 乳酸阈区（80-90%）
│   │   └── Zone 5 - 无氧区（90-100%）
│   └── 不同目标的心率训练
│       ├── 减脂训练
│       ├── 提升耐力
│       └── 提升速度
│
├── 03_柔韧度不好真的要命
├── 04_肌肉耐力让你更享受运动
├── 05_怎样应对发胖这件事
└── 06_发刊词_你需要从这门课中学到什么
```

每个知识点都包含：
- **面包屑导航**: `心率区间训练法 > 五区心率训练法 > Zone 2`
- **关键概念**: `["Zone 2", "有氧", "燃脂", "60-70%"]`
- **目标人群**: `["跑步爱好者", "减脂人群"]`
- **难度级别**: `intermediate`

---

## 💡 使用场景示例

### 场景 1: 用户创建减肥目标

**用户操作**:
```
创建目标:
- 类型: 减肥
- 当前体重: 75kg
- 目标体重: 65kg
- 期限: 3个月
```

**系统响应**:
```
✅ 目标已创建！基于张展晖《运动科学》课程，为您生成个性化训练计划：

📊 您的心率区间 (基于年龄35岁，静息心率60):
- Zone 1 (恢复): 110-120 bpm
- Zone 2 (燃脂): 120-135 bpm ⭐ 主要训练区间
- Zone 3 (有氧): 135-150 bpm
- Zone 4 (阈值): 150-165 bpm
- Zone 5 (极限): 165-180 bpm

🏃 周训练计划 (80/20法则):
周一: Zone 2 慢跑 45分钟
周二: 休息或力量训练
周三: Zone 4 节奏跑 30分钟
周四: Zone 2 慢跑 45分钟
周五: 休息
周六: Zone 2 长距离跑 90分钟
周日: Zone 1 恢复跑 30分钟

💡 训练要点:
• 80%时间保持在Zone 2，主要靠脂肪供能
• 每周1次Zone 4训练，提高代谢效率
• 配合饮食控制，每日热量赤字500千卡
• 预计每周减重0.5-1kg，3个月可达目标

📚 知识来源: 张展晖《心率区间训练法》《减脂训练》
```

### 场景 2: 用户准备运动

**用户操作**: 点击"开始运动"

**系统推送**:
```
🏃 今日训练建议 (2026-01-20 周一)

根据您的恢复状态:
• HRV: 65ms (良好)
• 身体电量: 78 (充足)
• 睡眠分数: 82 (优秀)

✅ 今日适合进行: Zone 2 有氧慢跑

📍 训练参数:
• 目标心率: 120-135 bpm
• 建议时长: 45-60分钟
• 强度感觉: 轻松，可以正常对话

💡 训练要点 (来自张展晖课程):
• 保持轻松配速，不要追求速度
• 主要用鼻子呼吸，如果需要张嘴说明强度过高
• 前10分钟热身，让心率逐渐上升
• 注意补水，每15分钟喝一小口

🎯 今日目标: 建立有氧基础，提高脂肪供能效率

准备好了吗？点击"开始记录"
```

### 场景 3: 运动结束

**系统分析**:
```
📊 运动分析报告

🏃 今日跑步 - 8.5km, 52分钟

❤️ 心率分析:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zone 1 (恢复):    ████░░░░░░░░░░░░░░░░  8%
Zone 2 (有氧):    ████████████████████  78% ✅
Zone 3 (耐力):    ████░░░░░░░░░░░░░░░░  14%
Zone 4 (阈值):    ░░░░░░░░░░░░░░░░░░░░  0%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 训练评价 (基于张展晖课程标准):
• 强度分配优秀！78%时间在Zone 2，符合有氧基础训练要求
• 配速控制良好，没有进入Zone 4
• 持续时间合理，有助于提高脂肪供能效率

📈 与上次对比:
• Zone 2占比提高5%，说明配速控制更好了
• 平均心率下降3 bpm，心肺功能在进步

💡 改进建议 (来自张展晖课程):
• 继续保持当前强度，建立有氧基础需要3-6个月
• 建议每周安排1次Zone 4节奏跑，提高乳酸阈值
• 注意恢复，下次训练建议间隔48小时

🔋 恢复建议:
• 预计恢复时间: 36-48小时
• 建议明天进行轻度拉伸或休息
• 注意补充蛋白质和碳水化合物

📚 参考: 张展晖《五区心率训练法》《恢复与预防》
```

---

## 📈 预期效果

### 用户体验提升

**之前**:
- ❌ 目标设定凭感觉，不科学
- ❌ 运动强度靠猜，容易过度或不足
- ❌ 数据展示为主，缺少指导

**之后**:
- ✅ 基于专业课程的科学目标设定
- ✅ 个性化心率区间，精准控制强度
- ✅ 全流程指导：运动前 → 运动中 → 运动后
- ✅ 知识来源可追溯，用户更信任

### 系统能力提升

- ✅ **知识驱动**: 基于专业课程，而非简单规则
- ✅ **个性化**: 结合用户画像和实时数据
- ✅ **可解释**: 每个建议都有知识来源
- ✅ **持续优化**: 根据用户反馈调整

---

## 🎯 下一步行动

### 立即可做

1. ✅ 上传张展晖课程（按照上面的步骤）
2. ✅ 测试知识检索和 RAG 问答
3. ⏳ 实现目标设定智能引导
4. ⏳ 实现运动前实时指导
5. ⏳ 增强运动后个性化分析

### 中期规划

- 添加更多专业课程（营养、恢复、力量训练）
- 实现多模型协作决策（GPT + Claude + Gemini）
- 开发 AI 教练对话功能
- 集成智能家居（自动调节运动环境）

### 长期愿景

打造一个真正的 **AI 健康管家**，不仅记录数据，更能：
- 🧠 理解用户目标和状态
- 📚 掌握专业健康知识
- 🎯 制定科学训练计划
- 💪 全程指导和激励
- 📊 持续评估和优化

---

## 📚 相关文档

### 技术文档
- [增强版知识库详细说明](./backend/KNOWLEDGE_BASE_ENHANCED.md)
- [知识库优化总结](./backend/KNOWLEDGE_BASE_OPTIMIZATION_SUMMARY.md)
- [上传指南](./backend/UPLOAD_GUIDE.md)

### 项目规划
- [Executor V2 路线图](./EXECUTOR_V2_ROADMAP.md)
- [系统架构](./ARCHITECTURE.md)

### API 文档
- [在线 API 文档](http://localhost:8000/docs)

---

## 🤝 需要帮助？

如果遇到问题，请查看：

1. **上传问题** → `backend/UPLOAD_GUIDE.md` 的"常见问题"部分
2. **技术问题** → `backend/KNOWLEDGE_BASE_ENHANCED.md`
3. **API 问题** → http://localhost:8000/docs

---

**祝你成功！让我们一起打造最智能的健康管理系统！** 🎉

---

**创建时间**: 2026-01-20  
**最后更新**: 2026-01-20  
**版本**: 1.0
