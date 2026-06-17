# 运动 GPS 数据缺失问题分析

**问题发现时间**: 2026-01-23  
**影响**: 最近的运动记录没有 GPS 数据和地图显示

## 🐛 问题描述

用户报告 https://health.westwetlandtech.com/workout 运动页面最近没有 GPS 数据和地图显示。

## 🔍 问题分析

### 受影响的记录

| ID | 日期 | 名称 | 类型 | 距离 | GPS数据 | 原因 |
|-----|------|------|------|------|---------|------|
| 51 | 2026-01-22 | 力量训练 | strength | 0 m | 无 | ✅ 室内运动，正常 |
| 50 | 2026-01-21 | 节奏 | running | 4,083 m | **缺失** | ❌ 应有但未同步 |
| 48 | 2026-01-19 | 登山 | hiking | 337 m | **缺失** | ❌ 应有但未同步 |
| 38 | 2026-01-18 | 基础训练 | running | 4,498 m | ✅ 有 (1,782点) | 正常 |

### 数据库检查结果

```sql
-- 最近 10 条有距离的运动记录
ID  | 日期       | 名称         | 类型    | 距离(m) | GPS数据大小
50  | 2026-01-21 | 节奏         | running |   4,083 | 无
48  | 2026-01-19 | 登山         | hiking  |     337 | 无
38  | 2026-01-18 | 基础训练     | running |   4,498 | 122,647字节 ✅
36  | 2026-01-17 | 追踪活动     | hiking  |     969 | 161,822字节 ✅
33  | 2026-01-16 | 登山         | hiking  |   1,763 | 32,500字节 ✅
```

**统计**:
- 有 GPS 数据: 8 条
- 无 GPS 数据: 2 条（活动 50, 48）

### 同步日志分析

#### 有 GPS 数据的活动（正常）

```
2026-01-21 12:45:43 [INFO] 活动 21550936217 获取到 1815 个GPS路线点
```

#### 缺失 GPS 数据的活动（异常）

```
# 活动 21614361036 (ID 50) - 跑步 4km
2026-01-22 18:57:06 [INFO] 活动 21614361036 从模拟曲线计算心率区间: [50, 110, 150, 970, 580]
2026-01-22 18:57:06 [INFO] 活动 21614361036 获取到 6 圈数据
# ❌ 没有 "获取到 GPS 路线点" 的日志

# 活动 21596080991 (ID 48) - 登山 337m
2026-01-22 18:57:06 [INFO] 活动 21596080991 使用模拟心率曲线 (50 点)
2026-01-22 18:57:06 [INFO] 活动 21596080991 从模拟曲线计算心率区间: [10, 30, 40, 250, 170]
# ❌ 没有 "获取到 GPS 路线点" 的日志
```

## 🎯 问题根源

### 可能的原因

1. **Garmin Connect API 返回的数据格式变化**
   - Garmin 可能更新了 API，GPS 数据字段名称或结构发生变化
   - 现有的解析逻辑无法识别新格式

2. **活动类型特殊**
   - 某些活动类型（如跑步机、室内跑步）可能没有 GPS 数据
   - 但日志显示这是户外跑步和登山，应该有 GPS

3. **同步时机问题**
   - 活动刚结束时 GPS 数据可能还未上传到 Garmin Connect
   - 需要延迟一段时间再同步

4. **API 权限或限制**
   - Garmin Connect 可能对 GPS 数据访问有限制
   - 需要特定的 API 调用才能获取

## ✅ 解决方案

### 方案 1: 手动重新同步（立即）

为受影响的活动手动触发 GPS 数据同步：

```python
# backend/scripts/resync_workout_gps.py
from app.database import SessionLocal
from app.services.workout_sync import WorkoutSyncService
from app.models.user import GarminCredential
import asyncio

async def resync_workout_gps(user_id: int, workout_ids: list):
    """重新同步指定运动的 GPS 数据"""
    db = SessionLocal()
    try:
        # 获取用户的 Garmin 凭证
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == user_id
        ).first()
        
        if not cred:
            print(f"用户 {user_id} 没有 Garmin 凭证")
            return
        
        # 创建同步服务
        sync_service = WorkoutSyncService(
            user_id=user_id,
            email=cred.garmin_email,
            password=None,  # 使用缓存的 session
            is_cn=cred.is_cn
        )
        
        # 重新同步每个活动
        for workout_id in workout_ids:
            print(f"正在重新同步活动 {workout_id}...")
            
            # 获取活动的 external_id
            workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.id == workout_id
            ).first()
            
            if not workout or not workout.external_id:
                print(f"  活动 {workout_id} 不存在或无 external_id")
                continue
            
            # 获取活动详细数据
            details = await sync_service.get_activity_details(
                int(workout.external_id)
            )
            
            if details and details.get('gps_data'):
                # 解析 GPS 数据
                route_points = sync_service._parse_gps_route(
                    details['gps_data']
                )
                
                if route_points:
                    import json
                    workout.route_data = json.dumps(route_points)
                    db.commit()
                    print(f"  ✅ 活动 {workout_id} 更新了 {len(route_points)} 个 GPS 点")
                else:
                    print(f"  ❌ 活动 {workout_id} 无法解析 GPS 数据")
            else:
                print(f"  ⚠️  活动 {workout_id} 没有 GPS 数据")
        
    finally:
        db.close()

# 运行
asyncio.run(resync_workout_gps(
    user_id=3,
    workout_ids=[50, 48]
))
```

### 方案 2: 增强 GPS 数据获取逻辑（长期）

#### 2.1 添加更多 GPS 数据源

```python
# backend/app/services/workout_sync.py

async def get_activity_details(self, activity_id: int):
    """获取活动详细数据（增强 GPS 数据获取）"""
    
    # 现有逻辑...
    
    # 🔑 新增: 尝试更多 GPS 数据源
    gps_data = None
    
    # 方法1: geoPolylineDTO (最可靠)
    if activity_details:
        gps_data = activity_details.get('geoPolylineDTO')
    
    # 方法2: 直接调用 GPS 数据 API
    if not gps_data:
        try:
            gps_response = self.client.get_activity_gps(activity_id)
            if gps_response:
                gps_data = gps_response
                logger.info(f"从 get_activity_gps 获取 GPS 数据")
        except Exception as e:
            logger.debug(f"get_activity_gps 失败: {e}")
    
    # 方法3: 从 TCX/GPX 文件获取
    if not gps_data:
        try:
            tcx_data = self.client.download_activity(
                activity_id, 
                dl_fmt=self.client.ActivityDownloadFormat.TCX
            )
            if tcx_data:
                gps_data = self._parse_tcx_gps(tcx_data)
                logger.info(f"从 TCX 文件获取 GPS 数据")
        except Exception as e:
            logger.debug(f"下载 TCX 失败: {e}")
    
    return {
        "details": details,
        "heart_rate_data": hr_data,
        "gps_data": gps_data,
        "lap_data": lap_data
    }
```

#### 2.2 添加 GPS 数据验证

```python
def _parse_gps_route(self, gps_data: Any) -> List[Dict]:
    """解析 GPS 路线数据（增强验证）"""
    route_points = []
    
    # 现有解析逻辑...
    
    # 🔑 新增: 验证 GPS 数据质量
    if route_points:
        # 检查是否有有效的坐标
        valid_points = [
            p for p in route_points
            if -90 <= p.get('lat', 0) <= 90 and
               -180 <= p.get('lng', 0) <= 180
        ]
        
        if len(valid_points) < len(route_points) * 0.9:
            logger.warning(
                f"GPS 数据质量差: {len(valid_points)}/{len(route_points)} 个有效点"
            )
        
        route_points = valid_points
    
    return route_points
```

#### 2.3 添加延迟重试机制

```python
async def sync_activities(self, start_date, end_date):
    """同步活动（添加 GPS 数据延迟重试）"""
    
    # 现有同步逻辑...
    
    # 🔑 新增: 对没有 GPS 数据的活动，标记为需要重试
    for activity in activities:
        parsed = self._parse_activity(activity, user_id)
        
        # 保存活动
        workout = self._save_workout(parsed, db)
        
        # 如果有距离但没有 GPS 数据，标记需要重试
        if (parsed.get('distance_meters', 0) > 100 and 
            not parsed.get('route_data')):
            
            # 设置一个标记字段，供后续重试
            workout.needs_gps_retry = True
            workout.gps_retry_count = 0
            db.commit()
            
            logger.warning(
                f"活动 {activity_id} 有距离但无 GPS 数据，标记为需要重试"
            )
```

### 方案 3: 添加 GPS 数据监控和告警

```python
# backend/app/services/monitoring.py

class WorkoutGPSMonitor:
    """运动 GPS 数据监控"""
    
    @staticmethod
    def check_gps_data_completeness(db: Session):
        """检查 GPS 数据完整性"""
        from sqlalchemy import text
        
        # 查询有距离但无 GPS 数据的活动
        query = text('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN route_data IS NULL THEN 1 ELSE 0 END) as missing_gps
            FROM workout_records
            WHERE distance_meters > 100
              AND workout_date >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        
        result = db.execute(query).fetchone()
        
        if result:
            total = result[0]
            missing = result[1]
            missing_rate = (missing / total * 100) if total > 0 else 0
            
            if missing_rate > 10:
                logger.warning(
                    f"GPS 数据缺失率过高: {missing}/{total} ({missing_rate:.1f}%)"
                )
                # 发送告警
                send_alert(
                    f"最近 7 天有 {missing} 个运动记录缺失 GPS 数据"
                )
```

## 📝 实施步骤

### 阶段 1: 紧急修复（立即）

1. **手动重新同步活动 50, 48 的 GPS 数据**
   ```bash
   cd /opt/health-app/backend
   python scripts/resync_workout_gps.py
   ```

2. **验证修复**
   - 访问 https://health.westwetlandtech.com/workout
   - 查看活动 50, 48 是否有地图显示

### 阶段 2: 增强同步逻辑（1-2 天）

1. **添加更多 GPS 数据源**
   - 实现 `get_activity_gps` API 调用
   - 支持从 TCX/GPX 文件解析

2. **添加数据验证**
   - GPS 坐标有效性检查
   - 数据质量评估

3. **添加延迟重试**
   - 标记需要重试的活动
   - 定时任务重新获取 GPS 数据

### 阶段 3: 监控和告警（1 周）

1. **添加 GPS 数据监控**
   - 统计缺失率
   - 异常告警

2. **用户通知**
   - GPS 数据缺失时提示用户
   - 提供手动重新同步按钮

## 🎯 预期效果

### 修复前

- ❌ 活动 50 (跑步 4km): 无地图
- ❌ 活动 48 (登山 337m): 无地图

### 修复后

- ✅ 活动 50: 显示跑步路线地图
- ✅ 活动 48: 显示登山路线地图
- ✅ 未来的活动: GPS 数据获取更可靠

## 📊 技术细节

### GPS 数据格式

Garmin Connect API 返回的 GPS 数据可能有多种格式：

#### 格式 1: geoPolylineDTO

```json
{
  "geoPolylineDTO": {
    "startPoint": {"lat": 30.266, "lon": 120.079},
    "endPoint": {"lat": 30.267, "lon": 120.081},
    "polyline": [
      {"lat": 30.266, "lon": 120.079, "time": 0},
      {"lat": 30.266, "lon": 120.079, "time": 10},
      ...
    ]
  }
}
```

#### 格式 2: encodedPolyline

```json
{
  "encodedPolyline": "u{r~FpxreM?A@A@?@A@?@A..."
}
```

#### 格式 3: gpsData 数组

```json
{
  "gpsData": [
    {"latitude": 30.266, "longitude": 120.079, "timestamp": 1234567890},
    ...
  ]
}
```

### 解析优先级

1. **geoPolylineDTO.polyline** (最可靠)
2. **encodedPolyline** (需要解码)
3. **gpsData 数组**
4. **TCX/GPX 文件**
5. **startPoint + endPoint** (最后手段)

## 🔗 相关文件

- **前端**: `frontend/src/app/workout/page.tsx`
- **地图组件**: `frontend/src/components/WorkoutMap.tsx`
- **同步服务**: `backend/app/services/workout_sync.py`
- **数据模型**: `backend/app/models/daily_health.py`

---

**问题分析完成，等待实施修复方案** 🚀
