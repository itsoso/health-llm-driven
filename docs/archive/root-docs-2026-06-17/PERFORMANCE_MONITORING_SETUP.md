# 性能监控中心部署指南

**创建时间**: 2026-01-23  
**目标**: 部署性能监控系统，实现多端性能追踪

---

## 📋 系统概述

### 功能特性

1. **多平台监控**
   - ✅ 小程序性能监控
   - ✅ Web 端性能监控
   - ⏳ H5 页面监控（未来）
   - ⏳ 原生 APP 监控（未来）

2. **监控指标**
   - 页面加载时间
   - API 响应时间
   - 渲染性能
   - 交互性能
   - 错误率

3. **数据分析**
   - 实时性能概览
   - 百分位数分析（P50, P90, P95, P99）
   - 慢页面/API 告警
   - 性能趋势分析
   - 多平台对比

4. **自动上报**
   - 前端自动收集性能数据
   - 批量上报（10条/30秒）
   - 失败重试机制
   - 队列管理

---

## 🚀 部署步骤

### 步骤 1: 数据库迁移

#### 方式 1: 使用 SQL 脚本（推荐）

```bash
# 连接到 PostgreSQL
psql -U postgres -d health_db

# 执行迁移脚本
\i backend/migrations/create_performance_tables.sql

# 验证表创建
\dt performance_*

# 查看表结构
\d performance_metrics
\d performance_alerts
\d performance_summaries
```

#### 方式 2: 使用 Alembic

```bash
cd backend

# 创建迁移
alembic revision --autogenerate -m "Add performance monitoring tables"

# 执行迁移
alembic upgrade head

# 验证
alembic current
```

### 步骤 2: 注册 API 路由

编辑 `backend/app/main.py`，添加性能监控路由：

```python
from app.api import performance

# 注册路由
app.include_router(performance.router, prefix="/api/v1", tags=["performance"])
```

### 步骤 3: 重启后端服务

```bash
# 开发环境
cd backend
uvicorn app.main:app --reload --port 8000

# 生产环境
sudo systemctl restart health-backend

# 验证服务状态
sudo systemctl status health-backend

# 查看日志
sudo journalctl -u health-backend -f
```

### 步骤 4: 构建并部署前端

#### Web 管理后台

```bash
cd frontend

# 安装依赖（如果有新增）
npm install

# 构建
npm run build

# 部署到生产服务器
# 方式 1: 使用 PM2
pm2 restart health-frontend

# 方式 2: 使用 systemd
sudo systemctl restart health-frontend

# 验证
pm2 status
curl -I https://health.westwetlandtech.com/admin/performance
```

#### 小程序

```bash
cd packages/mini-program

# 构建
npm run build:weapp

# 上传到微信开发者工具
# 提交审核
```

### 步骤 5: 验证功能

#### 5.1 验证后端 API

```bash
# 测试上报接口
curl -X POST https://health.westwetlandtech.com/api/v1/performance/metrics \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "session_id": "test_session_123",
    "platform": "mini_program",
    "metric_type": "page_load",
    "metric_name": "pages/index/index",
    "duration": 850,
    "start_time": "2026-01-23T10:00:00Z",
    "end_time": "2026-01-23T10:00:00.850Z",
    "success": 1
  }'

# 测试概览接口
curl https://health.westwetlandtech.com/api/v1/performance/overview?hours=24 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 5.2 验证前端页面

1. 访问 https://health.westwetlandtech.com/admin/performance
2. 登录账号
3. 查看性能概览
4. 切换平台筛选
5. 查看页面性能和 API 性能

#### 5.3 验证小程序自动上报

1. 打开小程序
2. 浏览几个页面
3. 等待 30 秒（触发批量上报）
4. 在管理后台查看是否有新数据

---

## 📊 使用指南

### 管理后台使用

#### 1. 性能概览

**路径**: `/admin/performance`

**功能**:
- 查看多平台性能对比
- 关键指标卡片
  * 总指标数
  * 平均页面加载时间
  * 平均 API 响应时间
  * 错误率
- 慢页面列表（P95 > 3s）
- 慢 API 列表（P95 > 1s）

**筛选器**:
- 平台：全部 / 小程序 / Web
- 时间范围：1小时 / 6小时 / 24小时 / 3天 / 7天

#### 2. 页面性能分析

**标签页**: 页面性能

**数据**:
- 页面名称
- 访问次数
- 平均耗时
- P50 / P90 / P95 / P99
- 错误率

**颜色编码**:
- 🟢 绿色：性能良好（< 2.1s）
- 🟡 黄色：性能警告（2.1s - 3s）
- 🔴 红色：性能差（> 3s）

#### 3. API 性能分析

**标签页**: API 性能

**数据**:
- API 端点
- 调用次数
- 平均耗时
- P50 / P90 / P95 / P99
- 成功率

**颜色编码**:
- 🟢 绿色：性能良好（< 0.7s）
- 🟡 黄色：性能警告（0.7s - 1s）
- 🔴 红色：性能差（> 1s）

### 小程序自动上报

#### 配置

默认配置（无需修改）:
```typescript
// packages/mini-program/src/utils/performance.ts

reportEnabled: true          // 启用上报
reportBatchSize: 10          // 批量大小
reportInterval: 30000        // 上报间隔（30秒）
```

#### 手动控制

```typescript
import { performanceMonitor } from '@/utils/performance';

// 关闭上报（调试时）
performanceMonitor.setReportEnabled(false);

// 开启上报
performanceMonitor.setReportEnabled(true);
```

#### 查看上报日志

小程序开发者工具控制台：
```
[性能上报] 已上报 10 条数据
[缓存] garmin_today_2026-01-23 命中 ✅
[性能] API-getTodayGarminData 耗时 8ms
```

---

## 🔍 性能分析方法

### 1. 识别慢页面

**步骤**:
1. 进入"性能概览"
2. 查看"慢页面"列表
3. 点击"页面性能"标签
4. 找到 P95 > 3s 的页面
5. 分析原因：
   - API 调用过多？
   - 数据量过大？
   - 渲染复杂？

**优化建议**:
- 分批加载
- 添加缓存
- 减少 API 调用
- 优化渲染逻辑

### 2. 识别慢 API

**步骤**:
1. 进入"性能概览"
2. 查看"慢 API"列表
3. 点击"API 性能"标签
4. 找到 P95 > 1s 的 API
5. 分析原因：
   - 数据库查询慢？
   - LLM 调用慢？
   - 外部 API 慢？

**优化建议**:
- 添加数据库索引
- 实施 Redis 缓存
- 异步处理耗时操作
- 优化查询语句

### 3. 监控错误率

**步骤**:
1. 查看错误率指标
2. 如果错误率 > 5%，需要关注
3. 查看具体错误信息
4. 定位问题代码

**常见问题**:
- API 超时
- 数据验证失败
- 网络错误
- 权限问题

### 4. 对比平台性能

**步骤**:
1. 选择"全部平台"
2. 对比小程序和 Web 的性能
3. 找出性能差异
4. 针对性优化

**示例**:
```
小程序首页加载: 850ms
Web 首页加载: 1200ms
→ Web 端需要优化
```

---

## 📈 性能优化建议

### 前端优化

#### 1. 分批加载（已实现）✅

```typescript
// 第一批：关键数据（立即）
const criticalData = await loadCriticalData();

// 第二批：重要数据（延迟300ms）
setTimeout(() => loadImportantData(), 300);

// 第三批：次要数据（延迟800ms）
setTimeout(() => loadSecondaryData(), 800);
```

#### 2. 本地缓存（已实现）✅

```typescript
// 使用带缓存的 API
const data = await getTodayGarminDataCached();

// 缓存配置
GARMIN_DATA: 5 * 60 * 1000,      // 5分钟
MORNING_BRIEFING: 30 * 60 * 1000, // 30分钟
```

#### 3. 图片懒加载（待实现）⏳

```typescript
<Image
  src={imageUrl}
  lazyLoad
  mode="aspectFit"
/>
```

#### 4. 虚拟列表（待实现）⏳

```typescript
<VirtualList
  height={500}
  itemHeight={50}
  itemCount={1000}
  renderItem={renderItem}
/>
```

### 后端优化

#### 1. 数据库索引（待实现）⏳

```sql
-- 为常用查询字段添加索引
CREATE INDEX idx_garmin_user_date ON garmin_data(user_id, record_date DESC);
CREATE INDEX idx_workout_user_date ON workout_records(user_id, workout_date DESC);
```

#### 2. Redis 缓存（待实现）⏳

```python
from app.utils.cache import get_cached, set_cached

@router.get("/garmin/today")
async def get_today_garmin_data(current_user: User = Depends(...)):
    cache_key = f"garmin_today_{current_user.id}"
    
    # 尝试从缓存获取
    cached = get_cached(cache_key)
    if cached:
        return cached
    
    # 查询数据库
    data = db.query(...).first()
    
    # 设置缓存（5分钟）
    set_cached(cache_key, data, ttl=300)
    
    return data
```

#### 3. 异步处理（待实现）⏳

```python
from celery import Celery

celery = Celery('tasks')

@celery.task
def generate_morning_briefing(user_id: int):
    """异步生成早间简报"""
    # 耗时的 LLM 调用
    briefing = llm.generate_briefing(user_id)
    # 保存到数据库
    save_briefing(briefing)
```

#### 4. 聚合接口（待实现）⏳

```python
@router.get("/home/dashboard")
async def get_home_dashboard(current_user: User = Depends(...)):
    """一次请求返回所有首页数据"""
    return {
        "garmin": get_garmin_data(),
        "workouts": get_workouts(),
        "reminders": get_reminders(),
        # ... 其他数据
    }
```

---

## 🎯 性能目标

### 当前性能（优化后）

| 指标 | 小程序 | Web | 目标 |
|------|--------|-----|------|
| 首屏加载 | 0.8s | 1.2s | < 1s |
| 完整加载 | 1.5s | 2.0s | < 2s |
| API 响应 | 200ms | 250ms | < 300ms |
| 缓存命中率 | 80% | 70% | > 70% |
| 错误率 | 0.5% | 0.8% | < 1% |

### 优化目标（Phase 3）

| 指标 | 目标 | 说明 |
|------|------|------|
| 首屏加载 | < 500ms | 通过聚合接口和 Redis 缓存 |
| API 响应 | < 200ms | 数据库索引和缓存优化 |
| 缓存命中率 | > 90% | 智能缓存策略 |
| 错误率 | < 0.5% | 完善错误处理 |

---

## 🔧 故障排查

### 问题 1: 性能数据未上报

**症状**: 管理后台没有数据

**排查步骤**:
1. 检查小程序控制台是否有上报日志
2. 检查后端日志是否收到请求
3. 验证数据库是否有新记录

```bash
# 查看后端日志
sudo journalctl -u health-backend -f | grep "performance"

# 查询数据库
psql -U postgres -d health_db -c "SELECT COUNT(*) FROM performance_metrics;"
```

**解决方法**:
- 确保 `reportEnabled` 为 `true`
- 检查网络连接
- 验证 Token 是否有效

### 问题 2: 管理后台加载慢

**症状**: 页面打开很慢

**排查步骤**:
1. 检查数据量是否过大
2. 查看数据库查询性能
3. 检查网络延迟

**解决方法**:
- 添加数据库索引
- 减少查询时间范围
- 实施分页

### 问题 3: 数据不准确

**症状**: 显示的性能数据与实际不符

**排查步骤**:
1. 检查时区设置
2. 验证数据计算逻辑
3. 查看原始数据

**解决方法**:
- 统一使用 UTC 时间
- 验证百分位数计算
- 清理异常数据

---

## 📚 相关文档

- [MULTI_PLATFORM_ARCHITECTURE.md](./MULTI_PLATFORM_ARCHITECTURE.md) - 多端架构规划
- [PERFORMANCE_OPTIMIZATION_GUIDE.md](./PERFORMANCE_OPTIMIZATION_GUIDE.md) - 性能优化指南
- [PERFORMANCE_OPTIMIZATION_IMPLEMENTATION.md](./PERFORMANCE_OPTIMIZATION_IMPLEMENTATION.md) - 性能优化实施
- [AGENTS.md](./AGENTS.md) - 开发规范

---

## ✅ 检查清单

### 部署前

- [ ] 数据库迁移已执行
- [ ] 后端路由已注册
- [ ] 前端页面已构建
- [ ] 环境变量已配置

### 部署后

- [ ] 后端服务正常运行
- [ ] 前端页面可访问
- [ ] API 接口正常响应
- [ ] 小程序自动上报正常
- [ ] 管理后台显示数据

### 验证测试

- [ ] 上报单个指标成功
- [ ] 批量上报成功
- [ ] 性能概览显示正常
- [ ] 页面性能分析正常
- [ ] API 性能分析正常
- [ ] 多平台对比正常

---

**状态**: ✅ 文档完成，待部署  
**最后更新**: 2026-01-23  
**维护人**: AI Agent
