# 快速开始指南

## 环境要求

- Python 3.9+
- Node.js 18+
- npm 或 yarn

## 后端设置

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少需要配置：
- `OPENAI_API_KEY`: 用于健康分析的OpenAI API密钥
- `DATABASE_URL`: 数据库连接（默认使用SQLite）

### 3. 初始化数据库

数据库表会在首次启动时自动创建。

### 4. 启动后端服务

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端服务将在 `http://localhost:8000` 启动。

API文档可在 `http://localhost:8000/docs` 查看。

## 前端设置

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动前端服务

```bash
npm run dev
```

前端应用将在 `http://localhost:3000` 启动。

## 使用流程

### 1. 创建用户

首先需要创建一个用户：

```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "birth_date": "1990-01-01",
    "gender": "男"
  }'
```

### 2. 录入基础健康数据

```bash
curl -X POST "http://localhost:8000/api/v1/basic-health" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "height": 175,
    "weight": 70,
    "systolic_bp": 120,
    "diastolic_bp": 80,
    "record_date": "2024-01-01"
  }'
```

### 3. 导入体检数据

可以通过JSON格式导入：

```bash
curl -X POST "http://localhost:8000/api/v1/medical-exams/import/json?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "exam": {
      "exam_date": "2024-01-01",
      "exam_type": "blood_routine",
      "body_system": "circulatory",
      "hospital_name": "XX医院"
    },
    "items": [
      {
        "item_name": "白细胞",
        "value": 6.5,
        "unit": "10^9/L",
        "reference_range": "3.5-9.5",
        "result": "正常",
        "is_abnormal": "normal"
      }
    ]
  }'
```

### 4. 同步Garmin数据

```bash
curl -X POST "http://localhost:8000/api/v1/data-collection/garmin/sync?user_id=1&target_date=2024-01-01&access_token=YOUR_TOKEN"
```

### 5. 进行健康分析

```bash
curl "http://localhost:8000/api/v1/analysis/user/1/issues"
```

### 6. 创建健康目标

```bash
curl -X POST "http://localhost:8000/api/v1/goals" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "goal_type": "exercise",
    "goal_period": "daily",
    "title": "每日运动30分钟",
    "target_value": 30,
    "target_unit": "分钟",
    "start_date": "2024-01-01"
  }'
```

### 7. 每日健康打卡

通过前端界面 `http://localhost:3000/checkin` 进行每日打卡。

## 主要功能

### 1. 数据收集
- Garmin可穿戴设备数据同步
- 体检数据导入（支持JSON、CSV、Excel）

### 2. 健康分析
- 基于LLM的健康问题识别
- 个性化健康建议生成

### 3. 目标管理
- 日/周/月/年度目标设置
- 目标进展追踪
- 基于分析结果自动生成目标

### 4. 健康打卡
- 每日健康活动记录
- 专项锻炼追踪（跑步、深蹲、太极拳、八段锦等）
- 个性化建议展示

## 注意事项

1. **Garmin API集成**：需要实现完整的OAuth认证流程才能使用Garmin数据同步功能。当前代码提供了框架，需要根据Garmin官方文档完善。

2. **OpenAI API**：健康分析功能需要配置OpenAI API密钥。如果没有配置，分析功能将返回提示信息。

3. **数据库**：默认使用SQLite，适合开发和测试。生产环境建议使用PostgreSQL。

4. **用户认证**：当前版本未实现用户认证，所有API都是开放的。生产环境需要添加认证机制。

## 故障排除

### 后端无法启动
- 检查Python版本（需要3.9+）
- 检查依赖是否安装完整：`pip install -r requirements.txt`
- 检查端口8000是否被占用

### 前端无法启动
- 检查Node.js版本（需要18+）
- 检查依赖是否安装：`npm install`
- 检查端口3000是否被占用

### API调用失败
- 确认后端服务已启动
- 检查API地址是否正确
- 查看后端日志了解错误信息

## 下一步

- 完善Garmin OAuth认证流程
- 添加用户认证和授权
- 实现更多数据可视化
- 添加数据导出功能
- 优化LLM提示词以提高分析质量

