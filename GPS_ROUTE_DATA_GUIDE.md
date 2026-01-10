# GPS 路线数据支持指南

## 概述

已为运动记录添加 GPS 路线数据支持，可以在运动详情页面显示地图和 GPS 路线。

## 数据库迁移

### 1. 执行迁移脚本

在服务器上执行以下 SQL 迁移：

```bash
# 连接到数据库
sqlite3 /opt/health-app/backend/health.db

# 执行迁移
ALTER TABLE workout_records ADD COLUMN route_data TEXT;

# 退出
.quit
```

或者使用迁移脚本：

```bash
cd /opt/health-app
sqlite3 backend/health.db < scripts/migrations/20260110_01_add_route_data.sql
```

## 功能说明

### 1. 数据库字段

- **字段名**: `route_data`
- **类型**: `TEXT` (JSON 格式)
- **格式**: `[{"lat": 39.9, "lng": 116.4, "elevation": 100, "time": 0}, ...]`

### 2. Garmin 同步

Garmin 同步服务会自动尝试获取 GPS 路线数据：

- 从 `get_activity()` 获取活动详情
- 从 `get_activity_gps()` 获取 GPS 数据
- 从 `get_activity_details()` 获取详细数据

支持的 GPS 数据格式：
- 编码的 polyline 字符串
- GPS 坐标数组
- geoPolylineDTO / geoPolyline

### 3. 数据解析

GPS 数据会被解析并采样：
- 每 10 秒一个点
- 自动去重
- 包含纬度、经度、海拔（如果有）、时间戳

### 4. 前端显示

运动详情页面会自动显示：
- 地图组件（使用 Leaflet）
- GPS 路线（蓝色线条）
- 起点标记（绿色）
- 终点标记（红色）

## 使用方法

### 1. 新同步的数据

新同步的 Garmin 活动会自动包含 GPS 数据（如果 Garmin 提供）。

### 2. 重新同步已有数据

对于已有的运动记录，需要重新同步才能获取 GPS 数据：

**方法 1: 通过 API 刷新单个记录**

```bash
# 刷新特定运动记录（需要先实现刷新 GPS 的 API）
POST /api/v1/workout/me/{workout_id}/refresh-gps
```

**方法 2: 重新同步所有活动**

```bash
# 重新同步最近 30 天的活动
POST /api/v1/workout/me/sync-garmin?days=30
```

注意：重新同步会跳过已存在的记录，需要先删除旧记录或修改同步逻辑。

### 3. 手动添加 GPS 数据

可以通过 API 手动创建包含 GPS 数据的运动记录：

```json
POST /api/v1/workout/me
{
  "workout_date": "2026-01-10",
  "workout_type": "hiking",
  "route_data": [
    {"lat": 39.9042, "lng": 116.4074, "elevation": 50, "time": 0},
    {"lat": 39.9052, "lng": 116.4084, "elevation": 55, "time": 10},
    ...
  ]
}
```

## 技术细节

### GPS 数据解析流程

1. **获取原始数据**: 从 Garmin API 获取活动详情
2. **识别格式**: 自动识别多种 GPS 数据格式
3. **解码处理**: 如果是编码的 polyline，进行解码
4. **数据转换**: 转换为统一格式 `{lat, lng, elevation?, time?}`
5. **采样优化**: 每 10 秒采样一个点，减少数据量
6. **存储**: 以 JSON 格式存储到数据库

### 支持的 GPS 数据格式

1. **编码的 polyline 字符串**
   ```python
   "encoded_polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
   ```

2. **GPS 坐标数组**
   ```json
   [
     {"latitude": 39.9, "longitude": 116.4, "elevation": 100},
     ...
   ]
   ```

3. **geoPolylineDTO**
   ```json
   {
     "geoPolylineDTO": {
       "polyline": "encoded_string",
       "points": [...]
     }
   }
   ```

## 故障排查

### 问题 1: 地图不显示

**可能原因**:
- 数据库中没有 `route_data` 数据
- GPS 数据格式不正确
- 前端解析失败

**解决方法**:
1. 检查数据库中是否有 `route_data` 字段
2. 检查 `route_data` 是否为有效的 JSON
3. 查看浏览器控制台错误信息

### 问题 2: GPS 数据为空

**可能原因**:
- Garmin 活动没有 GPS 数据（如室内运动）
- Garmin API 未返回 GPS 数据
- 同步时未获取 GPS 数据

**解决方法**:
1. 确认 Garmin 活动有 GPS 数据
2. 检查同步日志，查看是否获取到 GPS 数据
3. 重新同步活动

### 问题 3: 地图显示不正确

**可能原因**:
- GPS 坐标格式错误
- 坐标超出范围
- 地图组件配置问题

**解决方法**:
1. 检查 `route_data` 中的坐标是否有效
2. 确认坐标范围合理（纬度 -90 到 90，经度 -180 到 180）
3. 检查 Leaflet 地图配置

## 后续优化

1. **添加刷新 GPS 数据的 API**: 允许单独刷新已有记录的 GPS 数据
2. **优化数据采样**: 根据运动类型和时长智能采样
3. **添加路线分析**: 分析路线难度、爬升等
4. **支持离线地图**: 使用离线地图瓦片
5. **路线分享**: 支持导出和分享路线

## 相关文件

- `backend/app/models/daily_health.py`: 数据库模型
- `backend/app/services/workout_sync.py`: Garmin 同步服务
- `backend/app/schemas/workout.py`: API Schema
- `backend/app/api/workout.py`: API 端点
- `frontend/src/app/workout/page.tsx`: 前端页面
- `frontend/src/components/WorkoutMap.tsx`: 地图组件
