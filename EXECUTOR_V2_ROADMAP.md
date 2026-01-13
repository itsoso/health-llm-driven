# executor.life 健康模块重构计划

## 分支信息
- **分支名称**: `executor-v2`
- **创建日期**: 2026-01-13
- **目标**: 渐进式重构，构建完整的个人健康管理系统

---

## 已完成的工作

### Phase 1: 基础架构 ✅

#### 1. 数据模型设计
- [x] `UserProfile` - 用户画像模型
  - 基本信息（性别、年龄、身高、血型）
  - 健康目标（步数、睡眠、饮水、运动）
  - 疾病历史（慢性病、过敏、家族史）
  - 生活习惯（运动频率、饮食偏好、作息）
  - 工作环境
  - 设备信息
  
- [x] `HealthGoal` - 健康目标模型
  - 支持多种目标类型
  - 进度追踪
  - AI建议存储

- [x] `CheckinTemplate` - 打卡模板模型
  - 自定义打卡项目
  - 提醒配置
  - 统计数据

- [x] `CheckinRecord` - 打卡记录模型
  - 详细的打卡数据
  - 主观感受记录
  - 位置和媒体附件

#### 2. 数据库迁移
- [x] SQLite兼容的迁移脚本 (`012_add_user_profile_and_checkin.sql`)

#### 3. API Schemas
- [x] 用户画像相关 Schemas
- [x] 健康目标相关 Schemas
- [x] 打卡模板和记录相关 Schemas
- [x] 统计相关 Schemas

#### 4. API 端点
- [x] `/api/v1/profile/me` - 用户画像 CRUD
- [x] `/api/v1/profile/goals` - 健康目标管理
- [x] `/api/v1/checkin/templates` - 打卡模板管理
- [x] `/api/v1/checkin/records` - 打卡记录管理
- [x] `/api/v1/checkin/stats` - 打卡统计
- [x] `/api/v1/checkin/calendar` - 打卡日历

---

## 待完成的工作

### Phase 2: 功能完善 (预计2周)

#### 1. 前端页面
- [ ] 用户画像设置页面
- [ ] 打卡主页（今日待打卡、已完成）
- [ ] 打卡模板管理页面
- [ ] 打卡统计和日历页面
- [ ] 健康目标管理页面

#### 2. 小程序页面
- [ ] 打卡首页
- [ ] 快速打卡功能
- [ ] 打卡提醒推送

#### 3. AI 增强
- [ ] 基于用户画像的个性化建议
- [ ] 打卡数据分析和趋势预测
- [ ] 目标达成建议

### Phase 3: 知识库建设 ✅ (已完成基础架构)

#### 1. RAG 系统搭建
- [x] 向量数据库集成 (Chroma)
- [x] 文档解析器 (支持 txt/md/json)
- [x] 检索增强生成管道
- [x] 知识库管理 API

#### 2. 知识库内容
- [x] 基础健康知识初始化接口
- [ ] 冯雪健康课程内容导入
- [ ] 皮皮妈妈公众号内容导入
- [ ] 专业健康书籍内容

### Phase 4: 设备集成扩展 (进行中)

#### 1. Apple Watch 集成
- [ ] Apple Health API 研究
- [ ] 数据同步服务

#### 2. 环境数据 ✅
- [x] 天气API集成 (Open-Meteo)
- [x] 空气质量API集成
- [x] 环境健康建议服务
- [x] 早间健康简报
- [x] 户外运动适宜度评估
- [ ] 智能家居数据（小米/华为）

### Phase 5: 高级功能 (预计6周+)

#### 1. 疾病管理
- [ ] 慢性病追踪模块
- [ ] 预警指标系统
- [ ] 青少年近视追踪

#### 2. 体检报告
- [ ] OCR识别
- [ ] 数据结构化存储
- [ ] 趋势分析

---

## 文件结构

```
backend/app/
├── models/
│   ├── user_profile.py      # 用户画像模型 [NEW]
│   └── checkin.py           # 打卡系统模型 [NEW]
├── schemas/
│   ├── user_profile.py      # 用户画像 Schemas [NEW]
│   └── checkin.py           # 打卡系统 Schemas [NEW]
├── api/
│   ├── user_profile.py      # 用户画像 API [NEW]
│   ├── checkin.py           # 打卡系统 API [NEW]
│   └── knowledge.py         # 知识库管理 API [NEW]
└── services/
    └── knowledge/           # 知识库服务 [NEW]
        ├── __init__.py
        ├── vectorstore.py   # 向量存储服务 (Chroma)
        ├── document_loader.py # 文档加载器
        └── rag_pipeline.py  # RAG 检索增强生成管道

scripts/migrations/
└── 012_add_user_profile_and_checkin.sql  # 数据库迁移 [NEW]
```

---

## 默认打卡模板

系统预置了以下打卡模板：

### 运动类
- 💪 俯卧撑 (20个/天)
- 🦵 深蹲 (30个/天)
- 🏋️ 仰卧起坐 (30个/天)
- 🧘 平板支撑 (60秒/天)
- 🏃 跳绳 (200个/天)
- 🏢 爬楼梯 (10层/天)
- 🤸 拉伸 (10分钟/天)

### 健康类
- 👃 洗鼻 (2次/天)
- ❤️ 测血压 (1次/天)
- 🩸 测血糖 (1次/天)
- ⚖️ 称体重 (1次/天)

### 生活习惯类
- 💧 喝水 (2000ml/天)
- 🧘‍♂️ 冥想 (10分钟/天)
- 🌙 早睡 (1次/天)
- 📵 不看手机 (1小时/天)
- 🌳 户外活动 (30分钟/天)

### 用药类
- 💊 维生素D (1粒/天)
- 🦠 益生菌 (1粒/天)

---

## 如何测试

### 1. 执行数据库迁移
```bash
cd backend
sqlite3 health.db < ../scripts/migrations/012_add_user_profile_and_checkin.sql
```

### 2. 启动后端服务
```bash
cd backend
./start.sh
```

### 3. 测试 API
```bash
# 获取用户画像
curl -X GET "http://localhost:8000/api/v1/profile/me" \
  -H "Authorization: Bearer <token>"

# 更新用户画像
curl -X PUT "http://localhost:8000/api/v1/profile/me" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"height_cm": 175, "target_steps": 10000}'

# 初始化默认打卡模板
curl -X POST "http://localhost:8000/api/v1/checkin/templates/init-defaults" \
  -H "Authorization: Bearer <token>"

# 快速打卡
curl -X POST "http://localhost:8000/api/v1/checkin/records/quick" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"template_id": 1}'

# 获取今日打卡
curl -X GET "http://localhost:8000/api/v1/checkin/records/today" \
  -H "Authorization: Bearer <token>"
```

---

## 注意事项

1. **向后兼容**: 所有新功能都是增量添加，不影响现有功能
2. **数据库**: 当前仍使用 SQLite，后续迁移到 PostgreSQL
3. **测试**: 请先在开发环境测试，确认无误后再部署到生产环境

---

## 版本历史

- **v2.0.0** (2026-01-13)
  - 初始化 executor-v2 分支
  - 添加用户画像模型和 API
  - 添加打卡系统 2.0 模型和 API
  - 创建数据库迁移脚本
