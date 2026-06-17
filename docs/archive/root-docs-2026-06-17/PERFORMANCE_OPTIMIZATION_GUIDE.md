# 小程序首页性能优化指南

**创建时间**: 2026-01-23  
**问题**: 小程序首页打开很慢，提示"正在分析中"

---

## 📊 性能监控实施

### 1. 前端性能打点

#### 已添加的监控点

**文件**: `packages/mini-program/src/utils/performance.ts`

**功能**:
- ✅ 页面加载时间追踪
- ✅ API 调用时间追踪
- ✅ 数据处理时间追踪
- ✅ 自动生成性能报告
- ✅ 慢操作告警（>1s）

**使用示例**:
```typescript
// 追踪页面加载
pagePerformance.pageStart('首页');
pagePerformance.dataLoaded('首页');
pagePerformance.pageReady('首页');

// 追踪 API 调用
await performanceMonitor.trackAPI('getTodayGarminData', () => getTodayGarminData());

// 追踪自定义操作
performanceMonitor.start('数据处理');
// ... 处理逻辑 ...
performanceMonitor.end('数据处理');
```

#### 首页监控点

**文件**: `packages/mini-program/src/pages/index/index.tsx`

| 监控点 | 说明 | 阈值 |
|--------|------|------|
| 页面-首页 | 从页面显示到完全就绪 | < 3s |
| 首页-总数据加载 | 所有数据加载总时间 | < 2s |
| 首页-并行API调用 | 9个并行 API 调用 | < 1.5s |
| API-getTodayGarminData | Garmin 数据 | < 500ms |
| API-getDailyRecommendation | 每日推荐 | < 500ms |
| API-getMorningBriefing | 早间简报 | < 800ms |
| API-getAIRecommendation | AI 推荐 | < 1s |
| API-getCurrentReminders | 当前提醒 | < 300ms |
| API-getDailySchedule | 每日日程 | < 300ms |
| 首页-数据处理 | 数据处理和状态更新 | < 100ms |

### 2. 后端性能打点

#### 性能监控工具

**文件**: `backend/app/utils/performance_monitor.py`

**功能**:
- ✅ 上下文管理器追踪
- ✅ 函数装饰器追踪
- ✅ API 端点性能追踪
- ✅ 数据库查询性能追踪
- ✅ 慢操作自动告警

**使用示例**:
```python
from app.utils.performance_monitor import performance_monitor, track_api_performance

# 使用上下文管理器
with performance_monitor.track("数据库查询"):
    users = db.query(User).all()

# 使用装饰器
@performance_monitor.track_function("生成推荐")
def generate_recommendation(user_id):
    ...

# 追踪 API 端点
@track_api_performance("/api/v1/users")
async def get_users():
    ...
```

#### 性能中间件

**文件**: `backend/app/middleware/performance_middleware.py`

**功能**:
- ✅ 自动追踪所有 API 请求
- ✅ 记录响应时间
- ✅ 记录请求/响应大小
- ✅ 添加性能响应头
- ✅ 慢请求自动告警

**响应头**:
- `X-Response-Time`: 响应时间（ms）
- `X-Request-Size`: 请求体大小（bytes）
- `X-Response-Size`: 响应体大小（bytes）

---

## 🔍 性能瓶颈分析

### 当前问题诊断

#### 1. 并行 API 调用过多

**问题**: 首页同时发起 9 个 API 请求
```typescript
Promise.allSettled([
  getTodayGarminData(),           // 1
  getDailyRecommendation(),       // 2
  getTodayRhinitis(),             // 3
  getTodayWorkouts(),             // 4
  getTodayDietSummary(),          // 5
  getMorningBriefing(),           // 6
  getAIRecommendation(),          // 7
  getCurrentReminders(),          // 8
  getDailySchedule()              // 9
]);
```

**影响**:
- 🔴 网络并发限制（小程序最多 10 个并发）
- 🔴 服务器压力大
- 🔴 用户感知慢（最慢的 API 决定总时间）

**优化建议**:
1. **分批加载**: 关键数据优先，次要数据延迟加载
2. **合并接口**: 后端提供聚合接口
3. **缓存策略**: 使用本地缓存减少请求

#### 2. 某些 API 响应慢

**可能的慢 API**:
- `getMorningBriefing()` - 可能涉及 LLM 调用
- `getAIRecommendation()` - 可能涉及复杂计算
- `getDailyRecommendation()` - 可能涉及多表查询

**优化建议**:
1. **后端缓存**: Redis 缓存热数据
2. **异步生成**: 提前生成推荐，API 只读取
3. **数据库优化**: 添加索引，优化查询

#### 3. 数据处理和渲染

**问题**: 大量数据需要在前端处理和渲染

**优化建议**:
1. **虚拟列表**: 长列表使用虚拟滚动
2. **懒加载**: 图片和非关键内容懒加载
3. **分页加载**: 大数据集分页显示

---

## 🚀 优化方案

### 方案 1: 分批加载（推荐）⭐

#### 实施步骤

**Step 1**: 定义数据优先级

```typescript
// 关键数据（立即加载）
const criticalAPIs = [
  getTodayGarminData(),
  getCurrentReminders(),
  getTodayWorkouts()
];

// 重要数据（延迟 500ms）
const importantAPIs = [
  getDailyRecommendation(),
  getTodayDietSummary(),
  getDailySchedule()
];

// 次要数据（延迟 1000ms）
const secondaryAPIs = [
  getMorningBriefing(),
  getAIRecommendation(),
  getTodayRhinitis()
];
```

**Step 2**: 分批加载实现

```typescript
const loadHomeData = async () => {
  setHomeData(prev => ({ ...prev, loading: true }));
  
  try {
    // 第一批：关键数据（立即显示）
    const criticalResults = await Promise.allSettled(criticalAPIs);
    updateHomeData(criticalResults, ['garmin', 'reminders', 'workouts']);
    
    // 第二批：重要数据（延迟加载）
    setTimeout(async () => {
      const importantResults = await Promise.allSettled(importantAPIs);
      updateHomeData(importantResults, ['recommendation', 'diet', 'schedule']);
    }, 500);
    
    // 第三批：次要数据（延迟加载）
    setTimeout(async () => {
      const secondaryResults = await Promise.allSettled(secondaryAPIs);
      updateHomeData(secondaryResults, ['briefing', 'aiRecommendation', 'rhinitis']);
    }, 1000);
    
  } finally {
    setHomeData(prev => ({ ...prev, loading: false }));
  }
};
```

**优点**:
- ✅ 用户快速看到关键信息
- ✅ 减少首屏加载时间
- ✅ 降低服务器瞬时压力

**预期效果**:
- 首屏加载时间: 3s → **1s**
- 完整加载时间: 3s → **2.5s**

### 方案 2: 后端聚合接口

#### 实施步骤

**Step 1**: 创建聚合接口

```python
# backend/app/api/home.py

@router.get("/home/dashboard")
async def get_home_dashboard(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    首页数据聚合接口
    一次请求返回所有首页需要的数据
    """
    with performance_monitor.track("首页数据聚合"):
        # 并行查询所有数据
        garmin_data = get_today_garmin_data(db, current_user.id)
        workouts = get_today_workouts(db, current_user.id)
        reminders = get_current_reminders(db, current_user.id)
        # ... 其他数据
        
        return {
            "garmin": garmin_data,
            "workouts": workouts,
            "reminders": reminders,
            # ... 其他数据
        }
```

**Step 2**: 前端调用

```typescript
const loadHomeData = async () => {
  const data = await getHomeDashboard();
  setHomeData({
    ...data,
    loading: false
  });
};
```

**优点**:
- ✅ 只需 1 个 HTTP 请求
- ✅ 减少网络往返时间
- ✅ 后端可以优化并行查询

**预期效果**:
- HTTP 请求数: 9 → **1**
- 网络时间: 减少 **60%**

### 方案 3: 缓存策略

#### 本地缓存

```typescript
// utils/cache.ts
class LocalCache {
  private cache = new Map<string, { data: any; timestamp: number }>();
  private ttl = 5 * 60 * 1000; // 5 分钟
  
  get(key: string) {
    const item = this.cache.get(key);
    if (!item) return null;
    
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key);
      return null;
    }
    
    return item.data;
  }
  
  set(key: string, data: any) {
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    });
  }
}

export const localCache = new LocalCache();
```

**使用示例**:
```typescript
const getTodayGarminDataCached = async () => {
  const cacheKey = 'garmin_data_today';
  
  // 尝试从缓存获取
  const cached = localCache.get(cacheKey);
  if (cached) {
    console.log('[缓存] 使用缓存的 Garmin 数据');
    return cached;
  }
  
  // 缓存未命中，请求 API
  const data = await getTodayGarminData();
  localCache.set(cacheKey, data);
  
  return data;
};
```

#### 后端 Redis 缓存

```python
# backend/app/utils/cache.py
import redis
import json
from typing import Optional, Any

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_cached(key: str) -> Optional[Any]:
    """从 Redis 获取缓存"""
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_cached(key: str, value: Any, ttl: int = 300):
    """设置 Redis 缓存"""
    redis_client.setex(
        key,
        ttl,
        json.dumps(value, default=str)
    )

# 使用示例
@router.get("/garmin/today")
async def get_today_garmin_data(current_user: User = Depends(...)):
    cache_key = f"garmin_today_{current_user.id}"
    
    # 尝试从缓存获取
    cached = get_cached(cache_key)
    if cached:
        logger.info(f"[缓存命中] {cache_key}")
        return cached
    
    # 缓存未命中，查询数据库
    data = db.query(...).first()
    
    # 设置缓存（5 分钟）
    set_cached(cache_key, data, ttl=300)
    
    return data
```

**优点**:
- ✅ 大幅减少数据库查询
- ✅ 降低服务器负载
- ✅ 提高响应速度

**预期效果**:
- 缓存命中率: **80%+**
- 响应时间: 减少 **70%**

### 方案 4: 数据库优化

#### 添加索引

```sql
-- 为常用查询字段添加索引
CREATE INDEX idx_garmin_data_user_date ON garmin_data(user_id, record_date DESC);
CREATE INDEX idx_workout_record_user_date ON workout_records(user_id, workout_date DESC);
CREATE INDEX idx_diet_record_user_date ON diet_records(user_id, record_date DESC);
CREATE INDEX idx_health_reminder_user_time ON health_reminders(user_id, reminder_time);

-- 复合索引
CREATE INDEX idx_supplement_record_user_date_taken 
ON supplement_records(user_id, record_date, taken);
```

#### 查询优化

```python
# 优化前：N+1 查询
users = db.query(User).all()
for user in users:
    profile = db.query(UserProfile).filter_by(user_id=user.id).first()

# 优化后：使用 JOIN
users = db.query(User).options(
    joinedload(User.profile)
).all()

# 优化前：查询所有字段
data = db.query(GarminData).filter_by(user_id=user_id).all()

# 优化后：只查询需要的字段
data = db.query(
    GarminData.sleep_score,
    GarminData.steps,
    GarminData.calories_burned
).filter_by(user_id=user_id).all()
```

**预期效果**:
- 数据库查询时间: 减少 **50%**
- 慢查询数量: 减少 **80%**

---

## 📈 实施计划

### Phase 1: 性能监控（已完成）✅

- [x] 创建前端性能监控工具
- [x] 创建后端性能监控工具
- [x] 添加首页性能打点
- [x] 添加 API 性能中间件

### Phase 2: 快速优化（本周）

**优先级 🔴 高**:
1. [ ] 实施分批加载（方案 1）
2. [ ] 添加本地缓存
3. [ ] 优化慢 API（getMorningBriefing, getAIRecommendation）

**预期效果**:
- 首屏加载时间: **减少 60%**
- 用户体验: **显著提升**

### Phase 3: 深度优化（下周）

**优先级 🟡 中**:
1. [ ] 创建后端聚合接口（方案 2）
2. [ ] 实施 Redis 缓存（方案 3）
3. [ ] 添加数据库索引（方案 4）

**预期效果**:
- API 响应时间: **减少 70%**
- 服务器负载: **减少 50%**

### Phase 4: 持续优化（第3周）

**优先级 🟢 低**:
1. [ ] 图片懒加载
2. [ ] 虚拟列表
3. [ ] 代码分割
4. [ ] CDN 加速

---

## 🔧 使用指南

### 查看性能日志

#### 前端

```bash
# 小程序开发者工具控制台
# 搜索 "[性能]" 查看性能日志

# 性能报告示例
========== 性能报告 ==========
总计时项: 12
总耗时: 2850ms
平均耗时: 237.50ms
慢操作 (>1s): 2

慢操作详情:
  - API-getMorningBriefing: 1520ms
  - API-getAIRecommendation: 1180ms
==============================
```

#### 后端

```bash
# 查看 API 性能日志
tail -f logs/app.log | grep "API性能"

# 查看慢操作
tail -f logs/app.log | grep "慢操作"

# 查看性能指标
tail -f logs/app.log | grep "性能"
```

### 性能分析

```bash
# 分析最慢的 API
grep "API性能" logs/app.log | sort -t'|' -k3 -rn | head -10

# 统计 API 平均响应时间
grep "API性能" logs/app.log | awk -F'|' '{print $2, $3}' | \
  awk '{sum[$1]+=$2; count[$1]++} END {for (api in sum) print api, sum[api]/count[api]"ms"}'
```

---

## 📊 性能基准

### 目标指标

| 指标 | 当前 | 目标 | 优化后 |
|------|------|------|--------|
| 首屏加载时间 | ~3s | < 1s | **0.8s** |
| 完整加载时间 | ~3s | < 2s | **1.5s** |
| API 平均响应 | ~500ms | < 300ms | **200ms** |
| 慢 API 数量 | 2-3个 | 0个 | **0个** |
| 缓存命中率 | 0% | > 70% | **85%** |

### 监控告警

| 告警类型 | 阈值 | 处理 |
|---------|------|------|
| 单个 API > 1s | 1000ms | 立即优化 |
| 首屏加载 > 2s | 2000ms | 检查网络和 API |
| 数据库查询 > 500ms | 500ms | 添加索引或缓存 |
| 内存使用 > 80% | 80% | 检查内存泄漏 |

---

## 🎯 最佳实践

### 前端

1. **分批加载**: 关键数据优先，次要数据延迟
2. **本地缓存**: 缓存不常变化的数据
3. **懒加载**: 图片和非关键内容懒加载
4. **防抖节流**: 频繁操作使用防抖或节流
5. **性能监控**: 持续监控和优化

### 后端

1. **数据库索引**: 为常用查询字段添加索引
2. **查询优化**: 避免 N+1 查询，使用 JOIN
3. **Redis 缓存**: 缓存热数据，减少数据库压力
4. **异步处理**: 耗时操作使用异步任务
5. **性能监控**: 追踪慢查询和慢 API

---

## 📚 相关文档

- [性能监控工具](./packages/mini-program/src/utils/performance.ts)
- [后端性能监控](./backend/app/utils/performance_monitor.py)
- [性能中间件](./backend/app/middleware/performance_middleware.py)
- [AGENTS.md - 性能规范](./AGENTS.md#4-性能规范-)

---

**状态**: ✅ 监控已实施，优化进行中  
**下一步**: 实施分批加载和缓存策略  
**最后更新**: 2026-01-23
