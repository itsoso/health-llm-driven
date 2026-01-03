# 健康管理系统 (Health LLM-Driven System)

一个基于LLM的个性化健康管理系统，旨在帮助用户构建适合个人情况的健康系统，养成良好习惯。

## 系统功能

### 1. 个人基础健康数据管理
- **基础数据**：年龄、身高、体重、血压、血脂等体检记录数据
- **专项体检数据**：血常规、血脂相关、尿常规、免疫相关等
- **按身体系统分类**：神经、循环、呼吸、消化、泌尿、内分泌等系统

### 2. 疾病记录管理
- 医院检查情况记录
- 诊断结果追踪
- 治疗方案记录

### 3. 日常健康记录
- **可穿戴设备数据**（Garmin）：
  - 心率变异性 (HRV)
  - 心率数据
  - 睡眠数据（深度睡眠、快速眼动睡眠、浅睡眠）
  - 身体电量
  - 睡眠分数
- **日常锻炼**：Garmin未记录的运动
- **日常饮食**：食物摄入记录
- **日常饮水**：饮水量追踪
- **补剂摄入**：营养补充剂记录
- **户外活动时间**：太阳照射量

### 4. 健康打卡系统
- 每日健康打卡表
- 专项锻炼追踪（跑步、深蹲、太极拳、八段锦等）
- 基于个人情况的个性化锻炼指引

## 系统目标

1. **自动化数据收集**
   - 体检数据自动导入
   - Garmin数据自动同步

2. **健康问题识别**
   - 基于体检数据和Garmin健康数据
   - 明确指出当前存在的健康问题

3. **个性化健康指导**
   - 基于识别的问题给出详细建议
   - LLM驱动的智能分析

4. **目标管理系统**
   - 日/周/月/年度目标设置
   - 饮食、锻炼、睡眠等多维度目标
   - 详细的实现步骤
   - 每日进展追踪和督促

## 技术栈

- **后端**：Python + FastAPI
- **前端**：React + TypeScript
- **数据库**：SQLite (开发) / PostgreSQL (生产)
- **LLM集成**：OpenAI API / 本地LLM
- **数据收集**：Garmin API

## 项目结构

```
health-llm-driven/
├── backend/              # 后端服务
│   ├── app/
│   │   ├── models/      # 数据模型
│   │   ├── api/         # API路由
│   │   ├── services/    # 业务逻辑
│   │   │   ├── data_collection/  # 数据收集服务
│   │   │   ├── health_analysis/  # 健康分析服务
│   │   │   └── goal_management/  # 目标管理服务
│   │   └── utils/       # 工具函数
│   ├── requirements.txt
│   └── main.py
├── frontend/            # 前端应用
│   ├── src/
│   │   ├── components/  # React组件
│   │   ├── pages/       # 页面
│   │   ├── services/    # API服务
│   │   └── types/       # TypeScript类型
│   └── package.json
├── data/               # 数据文件
└── README.md
```

## 快速开始

### 后端设置

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

详细运行说明请查看 [RUN.md](./RUN.md)

### 前端设置

```bash
cd frontend
npm install
npm run dev
```

## 运行测试

### 后端测试

```bash
cd backend
# 安装测试依赖（已包含在requirements.txt中）
pip install -r requirements.txt

# 运行所有测试
pytest

# 运行测试并查看覆盖率
pytest --cov=app --cov-report=html

# 或使用测试脚本
./run_tests.sh
./run_tests.sh --coverage  # 包含覆盖率报告
```

测试说明请查看 [backend/tests/README.md](./backend/tests/README.md)

## 环境变量

创建 `.env` 文件：

```
OPENAI_API_KEY=your_api_key
GARMIN_API_KEY=your_garmin_key
DATABASE_URL=sqlite:///./health.db
```

## 文档

- [运行指南](./RUN.md) - 详细的运行说明和故障排除
- [快速开始](./QUICKSTART.md) - 基本使用流程
- [测试说明](./backend/tests/README.md) - 测试相关文档

## 许可证

MIT

