# 计圈/区间数据功能实现文档

## 概述

本文档记录了为运动详情页面添加"计圈"和"区间用时"功能的完整实现过程。

## 功能说明

用户在查看运动详情时，现在可以通过三个Tab查看不同维度的数据：
1. **统计信息** - 原有的详细统计数据
2. **计圈** - 每圈/分段的详细数据（距离、时间、心率、配速等）
3. **区间用时** - 心率区间分布数据

## 实现内容

### 1. 数据库层 (Backend)

#### 1.1 数据模型更新

**文件**: `backend/app/models/daily_health.py`

在 `WorkoutRecord` 模型中添加了新字段：
```python
lap_data = Column(Text)  # 计圈数据 [{"lap": 1, "distance": 1000, "duration": 300, "avg_hr": 150, "avg_pace": 300}, ...]
```

#### 1.2 数据库迁移

**文件**: `scripts/migrations/20260121_01_add_lap_data_to_workout.sql`

```sql
ALTER TABLE workout_records ADD COLUMN IF NOT EXISTS lap_data TEXT;
COMMENT ON COLUMN workout_records.lap_data IS '计圈数据 JSON: [{"lap": 1, "distance": 1000, "duration": 300, "avg_hr": 150, "avg_pace": 300, "elevation_gain": 10}, ...]';
```

**执行迁移**:
```bash
cd backend
sqlite3 health.db < ../scripts/migrations/20260121_01_add_lap_data_to_workout.sql
```

### 2. API层 (Backend)

#### 2.1 Schema更新

**文件**: `backend/app/schemas/workout.py`

添加了 `LapData` 数据模型：
```python
class LapData(BaseModel):
    """计圈/分段数据"""
    lap: int  # 圈数/分段编号
    distance: Optional[float] = None  # 距离（米）
    duration: Optional[int] = None  # 时长（秒）
    avg_hr: Optional[int] = None  # 平均心率
    max_hr: Optional[int] = None  # 最大心率
    avg_pace: Optional[int] = None  # 平均配速（秒/公里）
    avg_speed: Optional[float] = None  # 平均速度（km/h）
    elevation_gain: Optional[float] = None  # 爬升（米）
    elevation_loss: Optional[float] = None  # 下降（米）
    calories: Optional[int] = None  # 卡路里
    avg_cadence: Optional[int] = None  # 平均步频
    avg_power: Optional[int] = None  # 平均功率（瓦）
```

#### 2.2 新增API端点

**文件**: `backend/app/api/workout.py`

新增端点：`POST /workout/me/{workout_id}/refresh-laps`

功能：手动刷新指定运动记录的计圈数据（从Garmin获取）

### 3. Garmin同步服务 (Backend)

**文件**: `backend/app/services/workout_sync.py`

#### 3.1 新增方法

1. **`_parse_lap_data(lap_data: Dict[str, Any]) -> List[Dict[str, Any]]`**
   - 解析Garmin返回的计圈/分段数据
   - 支持多种数据格式（laps, lapDTOs, splits）
   - 提取每圈的距离、时间、心率、配速、海拔、卡路里等数据

2. **更新 `get_activity_details()`**
   - 在获取活动详情时同时获取计圈数据
   - 尝试从多个数据源获取（splits, activity_details, 直接API调用）

3. **更新 `sync_activities()`**
   - 在同步活动时自动解析并存储计圈数据
   - 更新已有记录时补充缺失的计圈数据

### 4. 前端实现 (Mini-Program)

**文件**: `packages/mini-program/src/pages/workout-detail/index.tsx`

#### 4.1 数据接口

```typescript
interface LapData {
  lap: number;
  distance?: number;
  duration?: number;
  avg_hr?: number;
  max_hr?: number;
  avg_pace?: number;
  avg_speed?: number;
  elevation_gain?: number;
  elevation_loss?: number;
  calories?: number;
  avg_cadence?: number;
  avg_power?: number;
}

interface WorkoutDetail {
  // ... 其他字段
  lap_data: string | null;  // JSON字符串
}
```

#### 4.2 Tab切换功能

添加了状态管理：
```typescript
const [activeTab, setActiveTab] = useState<'stats' | 'laps' | 'intervals'>('stats');
```

#### 4.3 UI组件

1. **Tab导航栏**
   - 三个Tab：统计信息、计圈、区间用时
   - 支持点击切换，带动画效果

2. **计圈列表**
   - 显示每圈的详细数据
   - 包括：圈数、时长、距离、配速、心率、爬升、卡路里等
   - 空状态提示

3. **区间用时**
   - 复用原有的心率区间显示组件
   - 显示5个心率区间的时长和百分比

### 5. 样式实现 (Mini-Program)

**文件**: `packages/mini-program/src/pages/workout-detail/index.scss`

新增样式：
- `.stats-tabs` - Tab导航栏
- `.tab-item` - Tab项（含active状态）
- `.laps-list` - 计圈列表
- `.lap-item` - 单圈数据卡片
- `.lap-stats` - 圈数据网格布局
- `.empty-state` - 空状态样式
- `fadeIn` 动画 - Tab切换动画

## 使用方法

### 1. 运行数据库迁移

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
sqlite3 health.db < ../scripts/migrations/20260121_01_add_lap_data_to_workout.sql
```

### 2. 重启后端服务

```bash
cd backend
./start.sh
```

### 3. 同步Garmin数据

有两种方式获取计圈数据：

#### 方式1: 自动同步（推荐）
在小程序中进行Garmin数据同步，系统会自动获取计圈数据。

#### 方式2: 手动刷新
对于已存在的运动记录，可以调用刷新接口：
```bash
curl -X POST "http://localhost:8000/workout/me/{workout_id}/refresh-laps" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. 查看效果

1. 打开小程序
2. 进入任意运动详情页
3. 点击"计圈"或"区间用时"Tab查看数据

## 数据流程

```
Garmin API
    ↓
WorkoutSyncService._parse_lap_data()
    ↓
WorkoutRecord.lap_data (JSON存储)
    ↓
GET /workout/me/{id} (API响应)
    ↓
Mini-Program解析并展示
```

## 数据格式示例

### Garmin原始数据（示例）
```json
{
  "laps": [
    {
      "lap": 1,
      "distance": 1000.5,
      "duration": 305,
      "averageHR": 145,
      "maxHR": 160,
      "averageSpeed": 3.28,
      "elevationGain": 12.5,
      "calories": 45
    }
  ]
}
```

### 存储格式（lap_data字段）
```json
[
  {
    "lap": 1,
    "distance": 1000.5,
    "duration": 305,
    "avg_hr": 145,
    "max_hr": 160,
    "avg_speed": 11.81,
    "elevation_gain": 12.5,
    "calories": 45
  }
]
```

## 技术要点

### 1. 数据解析兼容性

`_parse_lap_data()` 方法支持多种Garmin数据格式：
- `laps` / `lapDTOs` / `splits`
- 自动处理单位转换（毫秒→秒，m/s→km/h）
- 容错处理，缺失字段不影响其他数据

### 2. 性能优化

- 计圈数据以JSON格式存储，避免额外表关联
- 前端按需解析，不影响列表页性能
- Tab切换使用CSS动画，流畅体验

### 3. 用户体验

- 空状态友好提示
- 数据单位清晰标注
- 响应式布局，适配不同屏幕
- 动画过渡自然

## 后续优化建议

1. **数据可视化**
   - 添加每圈配速/心率对比图表
   - 显示配速趋势曲线

2. **数据分析**
   - 计算最快圈/最慢圈
   - 分析配速稳定性
   - 提供训练建议

3. **批量操作**
   - 批量刷新历史记录的计圈数据
   - 后台定时任务自动补全

4. **导出功能**
   - 支持导出计圈数据为CSV/Excel
   - 分享到社交平台

## 测试清单

- [x] 数据库迁移成功
- [x] API端点正常响应
- [x] Garmin数据解析正确
- [x] 前端Tab切换流畅
- [x] 计圈数据正确显示
- [x] 空状态正确显示
- [x] 样式适配正常

## 日志说明

### Backend日志
```
INFO - 用户 1 刷新运动 123 计圈数据: 10 圈
DEBUG - 解析计圈数据得到 10 圈
DEBUG - 从splits获取计圈数据
```

### Frontend日志
```
[WorkoutDetail] 加载数据成功: ID=123
[WorkoutDetail] 数据预览: lap_data: 有计圈数据
```

## 故障排查

### 问题1: 计圈数据为空

**可能原因**:
- Garmin未提供计圈数据（室内运动）
- 数据同步时未获取详细信息
- 运动类型不支持计圈

**解决方案**:
1. 检查Garmin Connect中是否有计圈数据
2. 手动调用 `/refresh-laps` 接口
3. 查看后端日志确认数据获取情况

### 问题2: Tab切换无响应

**可能原因**:
- 前端状态未更新
- 样式文件未加载

**解决方案**:
1. 检查浏览器控制台错误
2. 清除缓存重新加载
3. 确认SCSS文件已编译

## 版本信息

- 实现日期: 2026-01-21
- 后端版本: Python 3.12
- 前端框架: Taro 3.x
- 数据库: SQLite

## 相关文件清单

### Backend
- `backend/app/models/daily_health.py`
- `backend/app/schemas/workout.py`
- `backend/app/api/workout.py`
- `backend/app/services/workout_sync.py`
- `scripts/migrations/20260121_01_add_lap_data_to_workout.sql`

### Frontend
- `packages/mini-program/src/pages/workout-detail/index.tsx`
- `packages/mini-program/src/pages/workout-detail/index.scss`

## 遵循的开发规范

根据 `AGENTS.md` 规范：
- ✅ 所有用户数据查询带 `user_id` 过滤
- ✅ 添加了INFO级别日志记录
- ✅ 敏感操作有权限检查
- ✅ 数据库字段添加了注释
- ✅ API响应格式统一
- ✅ 错误处理完善

## 总结

本次实现完整添加了计圈和区间用时功能，包括：
- 数据库schema扩展
- Garmin数据同步增强
- API端点完善
- 前端UI/UX实现
- 样式美化

用户现在可以在运动详情页通过Tab切换查看详细的计圈数据和心率区间分布，提升了数据可视化和用户体验。
