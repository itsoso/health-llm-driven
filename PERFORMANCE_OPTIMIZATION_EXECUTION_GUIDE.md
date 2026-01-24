# 性能优化执行指南

> 基于性能监控数据的实战优化步骤

## 🎯 优化目标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 首页加载时间 | ~3s | < 1s | ↓ 67% |
| API 响应时间 | ~500ms | < 100ms | ↓ 80% |
| 数据库查询 | ~200ms | < 50ms | ↓ 75% |
| 缓存命中率 | 0% | > 80% | +80% |

---

## 📋 第一阶段：数据库索引优化（立即执行）

### 预计时间：30分钟
### 预期提升：数据库查询速度 ↑ 5-10倍

### 步骤 1: 备份数据库

```bash
# SSH 登录服务器
ssh root@health.westwetlandtech.com

# 备份数据库
pg_dump -U health_user -d health_db -F c -f /tmp/health_db_backup_$(date +%Y%m%d_%H%M%S).dump

# 验证备份
ls -lh /tmp/health_db_backup_*.dump
```

### 步骤 2: 执行索引创建

```bash
# 进入项目目录
cd /opt/health-app

# 拉取最新代码
git pull

# 执行索引创建脚本
sudo -u postgres psql -d health_db -f backend/migrations/add_performance_indexes.sql

# 或者使用 health_user
PGPASSWORD=your_password psql -U health_user -d health_db -f backend/migrations/add_performance_indexes.sql
```

### 步骤 3: 验证索引创建

```bash
# 查看所有索引
sudo -u postgres psql -d health_db -c "
SELECT 
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
"

# 查看索引总大小
sudo -u postgres psql -d health_db -c "
SELECT pg_size_pretty(SUM(pg_relation_size(indexrelid))) as total_index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public';
"
```

### 步骤 4: 测试查询性能

```bash
# 测试常用查询的性能
sudo -u postgres psql -d health_db -c "
EXPLAIN ANALYZE 
SELECT * FROM garmin_data 
WHERE user_id = 3 
AND record_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY record_date DESC;
"

# 应该看到 "Index Scan using idx_garmin_data_user_date"
```

### 预期结果

```
优化前:
  Planning Time: 0.5ms
  Execution Time: 200ms (Seq Scan)

优化后:
  Planning Time: 0.3ms
  Execution Time: 15ms (Index Scan)
  
提升: 13倍 ✅
```

---

## 📋 第二阶段：API 缓存实施（1-2天）

### 预计时间：2-3小时
### 预期提升：API 响应速度 ↑ 10-20倍（缓存命中时）

### 步骤 1: 安装 Redis

```bash
# 安装 Redis
apt-get update
apt-get install redis-server -y

# 启动 Redis
systemctl start redis-server
systemctl enable redis-server

# 验证 Redis
redis-cli ping
# 应该返回: PONG
```

### 步骤 2: 配置 Redis 连接

```bash
# 编辑后端配置
cd /opt/health-app/backend
nano .env

# 添加 Redis 配置
REDIS_URL=redis://localhost:6379/0
REDIS_TTL_DEFAULT=3600  # 默认缓存 1 小时
```

### 步骤 3: 安装 Python Redis 库

```bash
cd /opt/health-app/backend
source venv/bin/activate
pip install redis aioredis
pip freeze > requirements.txt
```

### 步骤 4: 实现缓存装饰器

创建 `backend/app/utils/cache.py`:

```python
"""Redis 缓存工具"""
import json
import redis
import logging
from functools import wraps
from typing import Optional, Any, Callable
from datetime import timedelta

logger = logging.getLogger(__name__)

# Redis 客户端
redis_client: Optional[redis.Redis] = None

def init_redis(redis_url: str):
    """初始化 Redis 连接"""
    global redis_client
    try:
        redis_client = redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        logger.info(f"✅ Redis 连接成功: {redis_url}")
    except Exception as e:
        logger.error(f"❌ Redis 连接失败: {e}")
        redis_client = None

def cache(
    key_prefix: str,
    ttl: int = 3600,
    key_builder: Optional[Callable] = None
):
    """
    缓存装饰器
    
    Args:
        key_prefix: 缓存键前缀
        ttl: 过期时间（秒）
        key_builder: 自定义键生成函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not redis_client:
                # Redis 不可用，直接执行
                return await func(*args, **kwargs)
            
            # 生成缓存键
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = f"{key_prefix}:{':'.join(map(str, args))}"
            
            try:
                # 尝试从缓存获取
                cached = redis_client.get(cache_key)
                if cached:
                    logger.info(f"[缓存命中] {cache_key}")
                    return json.loads(cached)
                
                # 缓存未命中，执行函数
                logger.info(f"[缓存未命中] {cache_key}")
                result = await func(*args, **kwargs)
                
                # 保存到缓存
                redis_client.setex(
                    cache_key,
                    ttl,
                    json.dumps(result, ensure_ascii=False, default=str)
                )
                
                return result
            except Exception as e:
                logger.error(f"[缓存错误] {cache_key}: {e}")
                # 缓存失败，直接执行
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def invalidate_cache(pattern: str):
    """清除匹配的缓存"""
    if not redis_client:
        return
    
    try:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info(f"[缓存清除] {len(keys)} 个键: {pattern}")
    except Exception as e:
        logger.error(f"[缓存清除失败] {pattern}: {e}")
```

### 步骤 5: 应用缓存到 API

修改 `backend/app/api/daily_recommendation.py`:

```python
from app.utils.cache import cache, invalidate_cache

@router.get("/me")
@cache(
    key_prefix="daily_rec",
    ttl=3600,  # 1小时
    key_builder=lambda current_user, **kwargs: f"daily_rec:{current_user.id}:{date.today()}"
)
async def get_my_recommendations(
    use_llm: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取每日健康建议（带缓存）"""
    # ... 原有逻辑 ...
```

### 步骤 6: 重启后端服务

```bash
# 重启后端
systemctl restart health-backend

# 查看日志
journalctl -u health-backend -f
# 应该看到: ✅ Redis 连接成功
```

### 步骤 7: 测试缓存效果

```bash
# 第一次请求（缓存未命中）
time curl -H "Authorization: Bearer <token>" \
  https://health.executor.life/api/v1/daily-recommendation/me

# 第二次请求（缓存命中）
time curl -H "Authorization: Bearer <token>" \
  https://health.executor.life/api/v1/daily-recommendation/me
```

### 预期结果

```
第一次请求（缓存未命中）:
  响应时间: 3000ms
  日志: [缓存未命中] daily_rec:3:2026-01-24

第二次请求（缓存命中）:
  响应时间: 50ms
  日志: [缓存命中] daily_rec:3:2026-01-24
  
提升: 60倍 ✅
```

---

## 📋 第三阶段：查询优化（持续进行）

### 预计时间：持续优化
### 预期提升：数据库负载 ↓ 50%

### 优化 1: 修复 N+1 查询

```python
# 优化前
@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    for user in users:
        user.profile = db.query(UserProfile).filter_by(user_id=user.id).first()
        user.garmin = db.query(GarminData).filter_by(user_id=user.id).first()
    return users

# 优化后
from sqlalchemy.orm import joinedload

@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).options(
        joinedload(User.profile),
        joinedload(User.garmin_data)
    ).all()
    return users
```

### 优化 2: 添加分页

```python
@router.get("/diet/records/me")
def get_my_diet_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size
    
    records = db.query(DietRecord).filter_by(
        user_id=current_user.id
    ).order_by(
        DietRecord.record_date.desc()
    ).offset(offset).limit(page_size).all()
    
    total = db.query(func.count(DietRecord.id)).filter_by(
        user_id=current_user.id
    ).scalar()
    
    return {
        "records": records,
        "total": total,
        "page": page,
        "page_size": page_size
    }
```

### 优化 3: 使用 select_in_loading

```python
# 对于一对多关系，使用 selectinload
from sqlalchemy.orm import selectinload

users = db.query(User).options(
    selectinload(User.diet_records),
    selectinload(User.supplement_records)
).all()
```

---

## 📊 性能监控和验证

### 1. 查看性能面板

```
访问: https://health.executor.life/admin/performance
查看: 
  - 页面加载时间趋势
  - API 响应时间分布
  - 慢查询 TOP 10
```

### 2. 查看数据库性能

```bash
# 查看慢查询
sudo -u postgres psql -d health_db -c "
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# 查看索引使用情况
sudo -u postgres psql -d health_db -c "
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC
LIMIT 10;
"
```

### 3. 查看 Redis 缓存统计

```bash
# 连接 Redis
redis-cli

# 查看缓存键数量
DBSIZE

# 查看缓存命中率
INFO stats
# 查看 keyspace_hits 和 keyspace_misses

# 查看内存使用
INFO memory
```

---

## ✅ 验收标准

### 第一阶段完成标准

- [ ] 所有索引创建成功
- [ ] 索引使用率 > 90%
- [ ] 数据库查询时间 < 100ms
- [ ] 无慢查询告警

### 第二阶段完成标准

- [ ] Redis 正常运行
- [ ] 缓存命中率 > 80%
- [ ] API 响应时间 < 200ms
- [ ] 缓存相关日志正常

### 第三阶段完成标准

- [ ] 无 N+1 查询
- [ ] 所有列表接口支持分页
- [ ] 数据库连接池正常
- [ ] 无数据库连接泄漏

---

## 🚨 回滚方案

### 如果索引导致问题

```bash
# 删除所有新创建的索引
sudo -u postgres psql -d health_db -c "
DROP INDEX IF EXISTS idx_garmin_data_user_date;
DROP INDEX IF EXISTS idx_diet_records_user_date;
-- ... 其他索引
"

# 恢复备份
pg_restore -U health_user -d health_db /tmp/health_db_backup_*.dump
```

### 如果缓存导致问题

```bash
# 停止 Redis
systemctl stop redis-server

# 清空缓存
redis-cli FLUSHALL

# 重启后端（不使用缓存）
systemctl restart health-backend
```

---

## 📈 预期效果总结

| 阶段 | 优化内容 | 预期提升 | 实施难度 |
|------|---------|---------|---------|
| 第一阶段 | 数据库索引 | 查询速度 ↑ 5-10倍 | ⭐ 简单 |
| 第二阶段 | API 缓存 | 响应速度 ↑ 10-20倍 | ⭐⭐ 中等 |
| 第三阶段 | 查询优化 | 数据库负载 ↓ 50% | ⭐⭐⭐ 复杂 |

**总体提升**: 
- 首页加载: 3s → 1s (↓ 67%)
- API 响应: 500ms → 100ms (↓ 80%)
- 用户体验: 😰 → 😊

---

## 📝 下一步

1. **立即执行第一阶段** - 数据库索引优化（30分钟）
2. **本周完成第二阶段** - API 缓存实施（2-3小时）
3. **持续进行第三阶段** - 查询优化（每周优化）

**开始执行**: 
```bash
ssh root@health.westwetlandtech.com
cd /opt/health-app
git pull
# 开始第一阶段...
```

---

**祝优化顺利！** 🚀
