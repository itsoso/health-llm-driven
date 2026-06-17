# 多端统一架构规划

**创建时间**: 2026-01-23  
**核心理念**: 一套后端服务，多套前端，以小程序为核心，确保小程序功能完整

---

## 🎯 架构目标

### 核心原则

1. **小程序优先**: 小程序是全功能版本，所有功能首先在小程序实现
2. **后端统一**: 一套 FastAPI 后端服务所有平台
3. **API 标准化**: 统一的 RESTful API 接口
4. **数据同步**: 所有平台共享同一数据库
5. **性能监控**: 统一的性能监控和诊断系统

### 平台支持

| 平台 | 状态 | 功能完整度 | 优先级 |
|------|------|-----------|--------|
| 小程序 | ✅ 已实现 | 100% | 🔴 最高 |
| Web 管理后台 | ✅ 已实现 | 80% | 🟡 高 |
| H5 页面 | ⏳ 规划中 | 0% | 🟢 中 |
| 原生 APP | ⏳ 规划中 | 0% | 🟢 低 |

---

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         用户层                               │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│   小程序     │   Web 端     │   H5 页面    │   原生 APP      │
│  (微信)      │  (浏览器)    │  (移动浏览器) │  (iOS/Android) │
└─────────────┴─────────────┴─────────────┴─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API 网关层                              │
│  - 统一认证 (JWT)                                            │
│  - 请求路由                                                  │
│  - 限流熔断                                                  │
│  - 性能监控                                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      业务服务层                              │
│  FastAPI Backend (Python 3.12)                             │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│  用户服务    │  健康数据    │  AI 服务     │  通知服务       │
│  - 认证授权  │  - Garmin   │  - LLM 推荐  │  - 提醒         │
│  - 用户画像  │  - 运动     │  - 数字孪生  │  - 日程         │
│             │  - 饮食     │  - 健康分析  │  - 告警         │
│             │  - 补剂     │             │                 │
└─────────────┴─────────────┴─────────────┴─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      数据存储层                              │
│  - PostgreSQL (主数据库)                                     │
│  - Redis (缓存 + 会话)                                       │
│  - OSS (文件存储)                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📱 小程序架构（核心）

### 技术栈

- **框架**: Taro 3.x (React)
- **语言**: TypeScript
- **状态管理**: React Hooks
- **UI 组件**: 自定义组件 + Taro UI
- **网络请求**: 统一封装的 request 模块
- **性能监控**: 自动上报到后端

### 功能模块

#### 1. 核心功能（已实现）✅

**首页**:
- AI 健康助手
- 早间简报
- 当前提醒
- 每日日程
- 运动指导
- 快速入口

**每日记录**:
- 鼻炎打卡
- 运动记录
- 饮食记录
- 补剂管理
- 体重记录

**数据看板**:
- Garmin 数据同步
- 健康趋势图表
- 运动统计
- 睡眠分析

**个人设置**:
- 用户画像
- Garmin 绑定
- 通知设置
- 隐私设置

#### 2. AI 功能（已实现）✅

- **智能推荐**: 基于用户画像和健康数据
- **数字孪生**: 个性化健康分析
- **补剂推荐**: 科学的补剂建议
- **饮食指导**: 智能饮食推荐
- **运动方案**: 个性化运动计划

#### 3. 性能优化（已实现）✅

- **分批加载**: 关键数据优先
- **本地缓存**: 智能缓存策略
- **性能监控**: 自动上报性能数据
- **首屏优化**: < 1s 首屏加载

### 小程序目录结构

```
packages/mini-program/
├── src/
│   ├── pages/              # 页面
│   │   ├── index/          # 首页（AI 助手）
│   │   ├── dashboard/      # 数据看板
│   │   ├── checkin/        # 每日记录
│   │   ├── settings/       # 个人设置
│   │   ├── supplements/    # 补剂管理
│   │   ├── workout/        # 运动记录
│   │   ├── diet/           # 饮食记录
│   │   └── ...
│   ├── services/           # 服务层
│   │   ├── api.ts          # API 调用
│   │   ├── cachedApi.ts    # 带缓存的 API
│   │   └── request.ts      # 请求封装
│   ├── utils/              # 工具函数
│   │   ├── performance.ts  # 性能监控
│   │   ├── cache.ts        # 缓存工具
│   │   └── ...
│   ├── types/              # 类型定义
│   └── app.tsx             # 入口文件
├── project.config.json     # 小程序配置
└── package.json
```

---

## 🖥️ Web 管理后台架构

### 技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **状态管理**: React Context
- **UI 组件**: Headless UI + 自定义组件
- **图表**: Recharts / Chart.js

### 功能模块

#### 1. 核心功能（已实现）✅

**数据看板**:
- 健康数据概览
- Garmin 数据同步
- 运动统计
- 睡眠分析

**记录管理**:
- 补剂管理
- 饮食记录
- 运动记录

**AI 功能**:
- 补剂推荐
- 饮食指导
- 运动方案

**个人设置**:
- 用户画像
- Garmin 绑定

#### 2. 管理功能（新增）✅

**性能监控中心** (本次新增):
- 实时性能概览
- 页面性能分析
- API 性能分析
- 慢查询告警
- 多平台对比

#### 3. 待实现功能 ⏳

- 用户管理
- 数据导出
- 系统设置
- 日志查询

### Web 目录结构

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── (auth)/             # 认证相关页面
│   │   ├── admin/              # 管理后台
│   │   │   └── performance/    # 性能监控（新增）
│   │   ├── overview/           # 数据看板
│   │   ├── supplements/        # 补剂管理
│   │   ├── workout/            # 运动记录
│   │   └── ...
│   ├── components/             # 组件
│   ├── contexts/               # Context
│   ├── services/               # 服务层
│   └── types/                  # 类型定义
├── public/                     # 静态资源
└── package.json
```

---

## 🔌 后端 API 架构

### 技术栈

- **框架**: FastAPI 0.115.0
- **语言**: Python 3.12
- **数据库**: PostgreSQL + SQLAlchemy
- **缓存**: Redis
- **认证**: JWT
- **文档**: OpenAPI (Swagger)

### API 设计原则

#### 1. RESTful 规范

```
GET    /api/v1/resource       # 获取列表
GET    /api/v1/resource/:id   # 获取详情
POST   /api/v1/resource       # 创建
PUT    /api/v1/resource/:id   # 更新
DELETE /api/v1/resource/:id   # 删除
```

#### 2. 统一响应格式

```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功",
  "timestamp": "2026-01-23T10:00:00Z"
}
```

#### 3. 错误处理

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数验证失败",
    "details": { ... }
  },
  "timestamp": "2026-01-23T10:00:00Z"
}
```

### API 模块

#### 1. 认证模块 (auth.py)

```python
POST   /api/v1/auth/wechat-login    # 微信登录
POST   /api/v1/auth/refresh          # 刷新 Token
POST   /api/v1/auth/logout           # 登出
GET    /api/v1/auth/me               # 获取当前用户
```

#### 2. 用户模块 (users.py)

```python
GET    /api/v1/users/me              # 获取用户信息
PUT    /api/v1/users/me              # 更新用户信息
GET    /api/v1/users/me/profile      # 获取用户画像
PUT    /api/v1/users/me/profile      # 更新用户画像
```

#### 3. Garmin 模块 (garmin.py)

```python
GET    /api/v1/garmin/my-data        # 获取 Garmin 数据
POST   /api/v1/garmin/sync           # 同步 Garmin 数据
GET    /api/v1/garmin/binding        # 获取绑定状态
POST   /api/v1/garmin/bind           # 绑定 Garmin
```

#### 4. 健康数据模块

```python
# 运动记录
GET    /api/v1/workouts              # 获取运动记录
POST   /api/v1/workouts              # 创建运动记录

# 饮食记录
GET    /api/v1/diet                  # 获取饮食记录
POST   /api/v1/diet                  # 创建饮食记录

# 补剂管理
GET    /api/v1/supplements           # 获取补剂列表
POST   /api/v1/supplements           # 添加补剂
```

#### 5. AI 服务模块

```python
POST   /api/v1/ai/recommendation     # 获取 AI 推荐
POST   /api/v1/supplements/scientific-recommendation  # 补剂推荐
POST   /api/v1/diet-recommendation   # 饮食推荐
POST   /api/v1/workout-plan          # 运动方案
```

#### 6. 性能监控模块 (performance.py) ✨ 新增

```python
POST   /api/v1/performance/metrics          # 上报单个指标
POST   /api/v1/performance/metrics/batch    # 批量上报指标
GET    /api/v1/performance/overview         # 性能概览
GET    /api/v1/performance/pages            # 页面性能
GET    /api/v1/performance/apis             # API 性能
GET    /api/v1/performance/trends           # 性能趋势
GET    /api/v1/performance/alerts           # 性能告警
```

### 后端目录结构

```
backend/
├── app/
│   ├── api/                    # API 路由
│   │   ├── auth.py             # 认证
│   │   ├── users.py            # 用户
│   │   ├── garmin.py           # Garmin
│   │   ├── supplements.py      # 补剂
│   │   ├── diet.py             # 饮食
│   │   ├── workout.py          # 运动
│   │   ├── performance.py      # 性能监控（新增）
│   │   └── ...
│   ├── models/                 # 数据模型
│   │   ├── user.py             # 用户模型
│   │   ├── daily_health.py     # 健康数据
│   │   ├── performance.py      # 性能监控（新增）
│   │   └── ...
│   ├── services/               # 业务逻辑
│   │   ├── digital_twin.py     # 数字孪生
│   │   ├── ai_scheduler.py     # AI 日程
│   │   └── ...
│   ├── utils/                  # 工具函数
│   │   ├── logger.py           # 日志
│   │   ├── performance_monitor.py  # 性能监控
│   │   └── ...
│   ├── middleware/             # 中间件
│   │   └── performance_middleware.py  # 性能中间件
│   └── main.py                 # 入口文件
├── tests/                      # 测试
├── logs/                       # 日志
└── requirements.txt            # 依赖
```

---

## 📊 性能监控系统（新增）

### 数据模型

#### 1. PerformanceMetric (性能指标)

```python
class PerformanceMetric:
    id: int
    user_id: int | None
    session_id: str
    platform: PlatformType  # mini_program, web, h5, app
    metric_type: MetricType  # page_load, api_call, render, interaction
    metric_name: str
    duration: float  # 毫秒
    start_time: datetime
    end_time: datetime
    details: dict | None
    metadata: dict | None
    success: int
    error_message: str | None
    created_at: datetime
```

#### 2. PerformanceAlert (性能告警)

```python
class PerformanceAlert:
    id: int
    alert_type: str  # slow_page, slow_api, high_error_rate
    severity: str  # critical, warning, info
    platform: PlatformType
    metric_name: str
    metric_value: float
    threshold: float
    description: str
    status: str  # open, acknowledged, resolved
    created_at: datetime
```

### 监控指标

| 指标类型 | 说明 | 阈值 |
|---------|------|------|
| 页面加载 | 页面完整加载时间 | < 3s |
| API 调用 | API 响应时间 | < 1s |
| 渲染性能 | 组件渲染时间 | < 100ms |
| 交互性能 | 用户交互响应时间 | < 200ms |
| 错误率 | 错误占比 | < 1% |

### 数据上报流程

```
1. 前端性能监控
   ↓
2. 本地队列缓存
   ↓
3. 批量上报（10条/30秒）
   ↓
4. 后端接收并存储
   ↓
5. 实时分析和告警
   ↓
6. 管理后台展示
```

---

## 🔄 数据同步策略

### 1. 实时同步

**场景**: 用户操作、状态变更

**流程**:
```
用户操作 → 前端更新 → API 调用 → 后端处理 → 数据库更新 → 返回结果
```

### 2. 定时同步

**场景**: Garmin 数据、AI 推荐

**流程**:
```
定时任务 → 调用第三方 API → 数据处理 → 存储到数据库 → 推送通知
```

### 3. 缓存策略

**多级缓存**:
```
L1: 前端本地缓存（5-30分钟）
L2: Redis 缓存（5-60分钟）
L3: 数据库（持久化）
```

---

## 🚀 部署架构

### 生产环境

```
┌─────────────────────────────────────────────────────────────┐
│                      Nginx (反向代理)                        │
│  - SSL 证书                                                  │
│  - 负载均衡                                                  │
│  - 静态资源                                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   Next.js (Web 前端)     │  │   FastAPI (后端 API)     │
│   - PM2 管理             │  │   - Systemd 管理         │
│   - 端口 3000            │  │   - 端口 8000            │
└──────────────────────────┘  └──────────────────────────┘
                                            │
                              ┌─────────────┴─────────────┐
                              │                           │
                              ▼                           ▼
                ┌──────────────────────┐  ┌──────────────────────┐
                │   PostgreSQL         │  │   Redis              │
                │   - 端口 5432        │  │   - 端口 6379        │
                └──────────────────────┘  └──────────────────────┘
```

### 域名规划

```
health.westwetlandtech.com          # Web 管理后台
api.health.westwetlandtech.com      # API 服务（未来）
```

---

## 📈 未来规划

### Phase 1: 性能监控（本次完成）✅

- [x] 后端性能监控 API
- [x] 前端自动上报
- [x] Web 管理后台页面
- [x] 多平台性能对比

### Phase 2: H5 页面（Q1 2026）

**目标**: 提供轻量级的 H5 页面，用于分享和快速访问

**功能**:
- 健康数据查看
- 运动记录分享
- 补剂推荐查看

**技术栈**:
- Next.js (SSR)
- Tailwind CSS
- 响应式设计

### Phase 3: 原生 APP（Q2 2026）

**目标**: 提供更好的用户体验和性能

**功能**:
- 完整的小程序功能
- 离线支持
- 推送通知
- 更好的性能

**技术栈**:
- React Native / Flutter
- 原生模块集成

### Phase 4: 数据分析平台（Q3 2026）

**目标**: 提供更强大的数据分析和可视化

**功能**:
- 高级数据分析
- 自定义报表
- 数据导出
- BI 集成

---

## 🎯 功能对比

### 各平台功能矩阵

| 功能模块 | 小程序 | Web 管理后台 | H5 页面 | 原生 APP |
|---------|--------|-------------|---------|----------|
| **核心功能** |
| 用户认证 | ✅ | ✅ | ⏳ | ⏳ |
| 用户画像 | ✅ | ✅ | ⏳ | ⏳ |
| Garmin 同步 | ✅ | ✅ | ❌ | ⏳ |
| **健康记录** |
| 鼻炎打卡 | ✅ | ❌ | ❌ | ⏳ |
| 运动记录 | ✅ | ✅ | ⏳ | ⏳ |
| 饮食记录 | ✅ | ✅ | ⏳ | ⏳ |
| 补剂管理 | ✅ | ✅ | ⏳ | ⏳ |
| **AI 功能** |
| 智能推荐 | ✅ | ✅ | ⏳ | ⏳ |
| 补剂推荐 | ✅ | ✅ | ⏳ | ⏳ |
| 饮食指导 | ✅ | ✅ | ⏳ | ⏳ |
| 运动方案 | ✅ | ✅ | ⏳ | ⏳ |
| **数据看板** |
| 健康概览 | ✅ | ✅ | ⏳ | ⏳ |
| 趋势图表 | ✅ | ✅ | ⏳ | ⏳ |
| **管理功能** |
| 性能监控 | ❌ | ✅ | ❌ | ⏳ |
| 用户管理 | ❌ | ⏳ | ❌ | ⏳ |
| 系统设置 | ❌ | ⏳ | ❌ | ⏳ |

**图例**:
- ✅ 已实现
- ⏳ 规划中
- ❌ 不支持

---

## 🔐 安全策略

### 1. 认证授权

- JWT Token 认证
- Token 过期自动刷新
- 多端登录状态同步

### 2. 数据安全

- HTTPS 加密传输
- 敏感数据加密存储
- 用户数据隔离

### 3. API 安全

- 请求签名验证
- 频率限制
- SQL 注入防护
- XSS 防护

---

## 📚 相关文档

- [PERFORMANCE_OPTIMIZATION_GUIDE.md](./PERFORMANCE_OPTIMIZATION_GUIDE.md) - 性能优化指南
- [PERFORMANCE_OPTIMIZATION_IMPLEMENTATION.md](./PERFORMANCE_OPTIMIZATION_IMPLEMENTATION.md) - 性能优化实施
- [AGENTS.md](./AGENTS.md) - 开发规范

---

**状态**: ✅ Phase 1 完成，Phase 2-4 规划中  
**核心原则**: 小程序优先，后端统一，多端协同  
**最后更新**: 2026-01-23
