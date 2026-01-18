# 🧬 executor.life 健康管理系统 - Vibe Coding 完整 Prompt

> 基于当前系统实际实现提取的完整重建指南，适用于 AI 辅助编程（Vibe Coding）

---

## 📋 项目概述

```
我要构建一个 AI 驱动的个人健康管理系统，名为 "executor.life"。

核心理念：让每个人都拥有专属的 AI 健康顾问团队。

系统的本质定位是：一个拥有用户完整认知、持续感知用户状态、主动替用户决策和行动的数字生命体。

区别于传统健康 App 的被动记录模式，这个系统要能够：
- 主动推送个性化建议，而非被动等待用户查询
- 基于规则引擎 + LLM 的双轨制智能分析
- 深度结合用户画像提供真正个性化的健康指导
- 时间感知，根据当前时间段给出合适建议
```

---

## 🏗️ 技术架构

```
技术栈要求：

后端：
- Python 3.12+ FastAPI
- SQLAlchemy ORM + SQLite（开发）/ PostgreSQL（生产）
- Pydantic 数据校验
- OpenAI GPT-4o-mini API
- ChromaDB 向量数据库（RAG）
- APScheduler 定时任务

前端：
- Next.js 14 (App Router)
- React 18 + TypeScript
- TailwindCSS
- @tanstack/react-query
- Recharts 数据可视化

项目结构：
health-llm-driven/
├── backend/
│   ├── app/
│   │   ├── api/           # RESTful API 路由
│   │   ├── models/        # SQLAlchemy 数据模型
│   │   ├── schemas/       # Pydantic 校验模型
│   │   ├── services/      # 业务逻辑层
│   │   │   ├── ai/        # AI 服务
│   │   │   ├── data_collection/  # 数据采集
│   │   │   ├── environment/      # 环境数据
│   │   │   └── knowledge/        # RAG 知识库
│   │   └── utils/         # 工具函数
│   ├── scripts/           # 脚本
│   └── tests/             # 测试
├── frontend/
│   └── src/
│       ├── app/           # 页面路由
│       ├── components/    # 组件
│       ├── contexts/      # Context
│       └── services/      # API 客户端
└── docs/
```

---

## 📊 核心数据模型

```
请创建以下数据模型：

1. User - 用户基础信息
   - 认证字段：email, username, hashed_password, is_active, is_admin, is_approved, invite_code
   - 微信认证：wechat_openid, wechat_unionid, wechat_session_key
   - 基础信息：name, avatar_url, birth_date, gender, phone
   - 时间戳：created_at, updated_at

2. GarminCredential - Garmin 凭证（加密存储）
   - garmin_email, encrypted_password, is_cn（中国区）
   - 同步状态：last_sync_at, sync_enabled, credentials_valid, requires_mfa
   - 错误追踪：last_error, error_count

3. UserProfile - 用户画像
   基本信息：gender, birth_date, height_cm, blood_type
   身体数据：current_weight_kg, target_weight_kg, body_fat_percentage, muscle_mass_kg
   健康目标：target_steps(8000), target_sleep_hours(7.5), target_water_ml(2000), target_exercise_minutes(30)
   疾病历史(JSON)：chronic_conditions, allergies, family_history, surgeries
   药物/补剂(JSON)：current_medications
   生活习惯：exercise_frequency, diet_preference, smoking_status, alcohol_consumption
   睡眠习惯：usual_sleep_time, usual_wake_time, sleep_environment(JSON)
   工作环境：work_type, work_hours_per_day, sitting_hours_per_day
   地理位置：city, timezone
   设备信息(JSON)：devices
   计算属性：age, bmi, bmi_category

4. GarminData - 每日健康数据
   用户和日期：user_id, record_date
   心率数据：avg_heart_rate, max_heart_rate, min_heart_rate, resting_heart_rate, hrv
   睡眠数据：sleep_score, total_sleep_duration(分钟), deep_sleep_duration, rem_sleep_duration, light_sleep_duration, awake_duration
   身体电量：body_battery_charged, body_battery_drained, body_battery_most_charged, body_battery_lowest
   压力：stress_level
   活动：steps, calories_burned, active_minutes
   有氧能力：vo2max, training_load

5. DailyRecommendation - 每日健康建议
   - user_id, recommendation_date, analysis_date
   - one_day_recommendation(JSON), seven_day_recommendation(JSON)

6. HealthGoal - 健康目标
   - goal_type (weight/exercise/sleep/water/habit/custom)
   - name, description, target_value, current_value, unit
   - start_date, target_date, status, priority
   - ai_suggestions(JSON)

7. CheckinRecord - 打卡记录
   - user_id, checkin_date, template_id
   - data(JSON), notes

8. WorkoutRecord - 运动记录
   - user_id, workout_date, activity_type
   - duration_minutes, distance_km, calories
   - avg_heart_rate, max_heart_rate
   - gps_data(JSON)

9. InvitationCode - 邀请码
   - code(unique), created_by, max_uses, current_uses
   - is_active, expires_at
```

---

## 🤖 AI 核心服务

### 1. LLMHealthAnalyzer - 大模型健康分析器

```
功能：
- 构建用户上下文（结合 UserProfile 的完整画像信息）
- 获取时间上下文（基于北京时间的时段感知）
- 构建健康数据 Prompt（包含昨日数据、趋势、规则分析、环境数据）
- 调用 OpenAI 生成个性化健康建议

Prompt 要求：
- 个性化优先：深度结合用户画像（健康目标、慢性病、生活习惯、工作环境）
- 目标导向：建议围绕用户设定的健康目标
- 慢性病关注：考虑用户的慢性病管理（如鼻炎、咽炎）
- 工作适配：根据工作类型和久坐时长给出可行建议
- 时间感知：
  - 上午步数少是正常的，不要批评，要鼓励安排锻炼计划
  - 下午/晚上才评估步数是否达标
- 环境适应：根据天气和空气质量推荐室内/室外运动

返回 JSON 格式：
{
  "health_summary": "健康状况总结（100字）",
  "key_insights": ["洞察1", "洞察2", "洞察3"],
  "sleep_advice": "睡眠建议",
  "activity_advice": "活动建议（时间感知）",
  "heart_health_advice": "心率建议",
  "recovery_advice": "恢复建议",
  "environment_advice": "环境运动建议",
  "exercise_recommendations": [
    {
      "type": "运动类型",
      "location": "室内/室外",
      "duration": "时长",
      "intensity": "强度",
      "best_time": "最佳时间",
      "reason": "推荐原因"
    }
  ],
  "today_focus": "今日最应关注的一件事",
  "today_actions": ["行动1", "行动2", "行动3"],
  "warnings": ["健康风险警告"],
  "encouragement": "鼓励话语"
}
```

### 2. AIScheduler - AI 日程编排引擎

```
功能：
- 生成早间健康简报（Morning Briefing）
- 获取当前时间段的提醒（前后15分钟窗口）
- 生成每日日程安排（基于用户画像的作息习惯）
- 时间感知实时建议

默认提醒列表（ReminderType）：
- 07:00 早间洗鼻（nasal_wash）- 优先级1
- 07:10 晨起称重（weigh）- 优先级2
- 07:15 早起喝水（drink_water）- 优先级1
- 08:00 早餐补剂（supplement）- 优先级2
- 10:00/14:30/17:30 喝水提醒
- 10:30/15:30 起身活动（stand_up）
- 12:00 午餐记录（meal）
- 18:30 运动时间（exercise）- 条件：今日未运动
- 21:00 晚间洗鼻
- 21:30 晚间补剂
- 22:30 准备休息（sleep）

时间段问候语：
- 5-9点：早安！新的一天开始了 🌅
- 9-12点：上午好！保持专注 💪
- 12-14点：中午好！记得休息 ☀️
- 14-18点：下午好！继续加油 🚀
- 18-22点：晚上好！放松一下 🌙
- 22-5点：夜深了，注意休息 💤
```

### 3. RAGPipeline - 知识库检索增强生成

```
功能：
- 从 ChromaDB 检索相关知识（相关度阈值 > 0.3）
- 将知识库内容与用户数据结合
- 生成带来源引用的专业健康建议
- 增强每日 AI 建议（enhance_daily_advice）

知识分类：
- sleep：睡眠相关
- exercise：运动相关
- nutrition：营养相关
- mental_health：心理健康
- chronic_disease：慢性病管理
```

### 4. DailyRecommendationService - 规则引擎 + AI 双轨制

```
分析维度：
- 睡眠分析：评估睡眠分数、时长、深睡/REM比例
- 活动分析：评估步数、活动分钟数、达标情况
- 心率分析：评估静息心率、HRV、异常波动
- 压力/恢复分析：评估压力水平、身体电量变化

规则示例：
- 睡眠分数 < 60：状态差
- 步数 < 5000：活动严重不足
- 静息心率 > 80：偏高需关注
- 身体电量峰值 < 50：恢复不足
```

---

## 🔗 API 端点设计

```
认证模块 /api/v1/auth：
- POST /register - 注册（需要邀请码）
- POST /login - 登录
- POST /wechat/login - 微信小程序登录
- GET /me - 获取当前用户
- PUT /password - 修改密码

用户画像 /api/v1/profile：
- GET /me - 获取我的画像
- PUT /me - 更新我的画像
- GET /me/goals - 获取我的健康目标
- POST /me/goals - 创建健康目标

Garmin 数据 /api/v1/garmin：
- POST /connect - 绑定 Garmin 账号
- POST /sync - 手动触发同步
- GET /data - 获取健康数据（支持日期范围）
- GET /analysis - 获取综合分析

每日建议 /api/v1/daily-recommendation：
- GET /today - 获取今日 AI 建议（结合规则+LLM）
- GET /history - 获取历史建议

AI 日程 /api/v1/ai-scheduler：
- GET /morning-briefing - 获取早间简报
- GET /reminders - 获取当前时段提醒
- GET /schedule - 获取今日日程
- GET /recommendation - 获取时间感知建议

打卡系统 /api/v1/checkin：
- POST / - 提交打卡
- GET /today - 获取今日打卡状态
- GET /history - 打卡历史
- GET /templates - 获取打卡模板

知识库 /api/v1/knowledge：
- POST /ask - 基于知识库问答
- GET /search - 搜索知识内容
- POST /import - 导入知识文档（管理员）

环境数据 /api/v1/environment：
- GET /weather - 获取天气
- GET /air-quality - 获取空气质量
- GET /exercise-suitability - 获取运动适宜度评估

管理后台 /api/v1/admin：
- GET /users - 用户列表
- GET /applications - 注册申请列表
- POST /applications/{id}/approve - 审批
- POST /invitations - 创建邀请码
```

---

## 🎨 前端页面

```
页面列表：

1. 登录页 /login
   - 邮箱/密码登录
   - 微信小程序登录（显示二维码）

2. 注册页 /register
   - 邀请码验证
   - 基本信息填写

3. Dashboard /dashboard - 核心仪表盘
   - 今日实时数据卡片（睡眠、步数、心率、身体电量、HRV、压力）
   - 每5分钟自动刷新
   - 关键指标卡片（7天平均）
   - 趋势图表（睡眠分数、步数折线图/柱状图）

4. 每日洞察 /daily-insights
   - AI 生成的健康总结
   - 关键洞察卡片
   - 分类建议（睡眠/活动/心率/恢复/环境）
   - 今日行动清单
   - 运动推荐

5. AI 助手 /ai-assistant
   - 对话式健康问答
   - 知识库检索结果展示
   - 引用来源显示

6. 用户画像 /profile
   - 基本信息编辑
   - 健康目标设置
   - 慢性病/过敏史管理
   - 生活习惯设置

7. Garmin 数据 /garmin
   - Garmin 账号绑定
   - 同步状态显示
   - 历史数据列表
   - 详细数据展示

8. 目标管理 /goals
   - 目标列表
   - 进度追踪
   - AI 建议

9. 打卡 /checkin
   - 今日打卡
   - 打卡模板选择
   - 历史记录

10. 体检报告 /medical-exams
    - PDF 上传解析
    - 历史报告列表
    - 指标趋势

11. 运动记录 /workout
    - 运动列表
    - GPS 路线地图展示（Leaflet）
    - 运动详情

12. 设置 /settings
    - 账号管理
    - 通知设置
    - 设备管理

UI 风格要求：
- 现代渐变风格（indigo-purple 主色调）
- 玻璃态效果（backdrop-blur）
- 圆角卡片（rounded-xl/2xl）
- 图标 emoji 点缀
- 响应式设计（grid 布局）
- 深色 header，白色内容区域
```

---

## 🔐 安全规范

```
强制要求：
1. 所有密码使用 bcrypt 加密存储
2. Garmin 凭证使用 Fernet 对称加密
3. 所有 API 密钥通过环境变量获取
4. 用户数据查询强制带 user_id 过滤（数据隔离）
5. JWT Token 认证
6. 敏感操作记录审计日志
7. CORS 配置限制来源域名（生产环境）
8. 请求频率限制（如登录 5次/分钟）
9. 依赖版本锁定，禁用 alpha/beta 版本
10. 日志脱敏（不打印密码、token、个人数据）
```

---

## 📝 环境变量

```bash
# 数据库
DATABASE_URL=sqlite:///./health.db

# JWT
SECRET_KEY=your-super-secret-key-change-in-production

# OpenAI
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=  # 可选，代理地址
OPENAI_MODEL=gpt-4o-mini

# Garmin 加密
GARMIN_ENCRYPTION_KEY=your-fernet-key

# 环境数据 API
WEATHER_API_KEY=xxxxx

# 微信小程序
WECHAT_APPID=xxxxx
WECHAT_SECRET=xxxxx
```

---

## 🚀 启动命令

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev
```

---

## 📌 开发优先级

```
Phase 1 - 基础功能（2周）：
1. 用户注册/登录（邀请码制）
2. 用户画像 CRUD
3. Garmin 数据同步和存储
4. 基础 Dashboard 展示

Phase 2 - AI 能力（2周）：
1. 规则引擎分析
2. LLM 健康建议生成
3. 每日洞察页面
4. 时间感知建议

Phase 3 - 高级功能（2周）：
1. 知识库 RAG 系统
2. AI 日程编排
3. 打卡系统
4. 运动记录 + GPS 路线
```

---

## 📚 依赖清单

### 后端 requirements.txt

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sqlalchemy>=2.0.23
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-dotenv>=1.0.0
openai>=1.3.0
httpx>=0.25.2
python-dateutil>=2.8.2
pandas>=2.1.3
numpy>=1.26.2
alembic>=1.12.1
python-multipart>=0.0.6
# 用户认证
passlib[bcrypt]>=1.7.4
python-jose[cryptography]>=3.3.0
bcrypt>=4.0.1
cryptography>=41.0.0
email-validator>=2.0.0
# PDF解析
pypdf>=3.17.0
pdfplumber>=0.10.3
# 知识库RAG系统
chromadb>=0.4.22
# 测试
pytest>=7.4.3
pytest-asyncio>=0.21.1
pytest-cov>=4.1.0
psutil>=5.9.0
```

### 前端 package.json 依赖

```json
{
  "dependencies": {
    "@tanstack/react-query": "^5.12.2",
    "@types/leaflet": "^1.9.21",
    "axios": "^1.6.2",
    "date-fns": "^2.30.0",
    "leaflet": "^1.9.4",
    "next": "^14.0.4",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-leaflet": "^4.2.1",
    "recharts": "^2.10.3"
  },
  "devDependencies": {
    "@types/node": "^20.10.5",
    "@types/react": "^18.2.45",
    "@types/react-dom": "^18.2.18",
    "autoprefixer": "^10.4.16",
    "eslint": "^8.56.0",
    "eslint-config-next": "^14.0.4",
    "postcss": "^8.4.32",
    "tailwindcss": "^3.3.6",
    "typescript": "^5.3.3"
  }
}
```

---

## 🎯 使用建议

使用 Vibe Coding 重建系统时：

1. **按 Phase 逐步提出需求**：每次聚焦一个模块
2. **先数据模型，后 API，再前端**：保持层次清晰
3. **提供完整上下文**：将本文档作为项目背景提供给 AI
4. **迭代优化**：先实现核心功能，再逐步完善细节

---

*生成日期: 2026-01-18*
*基于 executor.life 健康模块 v2.3.0 提取*
