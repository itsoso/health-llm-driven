# 心率区间分析修复说明

## 问题描述

在 https://health.westwetlandtech.com/workout 页面，训练结束后的"❤️ 心率区间分析"显示所有区间都是 0%，没有拿到正确的数据。

## 根本原因

经过代码分析，发现问题的根本原因是：

1. **数据库字段存在但未被填充**：`WorkoutRecord` 模型定义了 `hr_zone_1_seconds` 到 `hr_zone_5_seconds` 字段，但这些字段在从 Garmin 同步数据时，可能因为以下原因没有被正确填充：
   - Garmin API 的 `hrTimeInZones` 字段可能不存在或为空
   - 不同类型的活动可能不返回心率区间数据
   - 某些 Garmin 设备可能不记录心率区间

2. **缺少备用方案**：当 Garmin 不提供心率区间数据时，系统没有从心率时间序列数据计算心率区间的备用逻辑。

## 解决方案

### 1. 添加心率区间计算功能

在 `backend/app/services/workout_sync.py` 中添加了 `_calculate_hr_zones_from_samples()` 方法：

```python
def _calculate_hr_zones_from_samples(
    self, 
    hr_samples: List[Dict[str, int]], 
    max_hr: int = 180
) -> List[int]:
    """
    从心率采样数据计算心率区间时长
    
    心率区间定义（基于最大心率百分比）：
    - Zone 1: 50-60% (恢复区)
    - Zone 2: 60-70% (燃脂区)
    - Zone 3: 70-80% (有氧区)
    - Zone 4: 80-90% (乳酸阈值区)
    - Zone 5: 90-100% (最大心率区)
    """
```

该方法：
- 接收心率采样点数组 `[{"time": seconds, "hr": bpm}, ...]`
- 根据最大心率计算各区间的阈值
- 统计每个采样点所在的区间，累计时长
- 返回 5 个区间的秒数

### 2. 在数据同步时自动计算心率区间

修改了 `sync_activities()` 方法，在以下情况下自动计算心率区间：

1. **从 Garmin 获取到心率时间序列数据时**：
   ```python
   if hr_points:
       parsed["heart_rate_data"] = json.dumps(hr_points)
       
       # 如果心率区间数据为空，从心率采样计算
       total_zone_seconds = sum([...])
       if total_zone_seconds == 0:
           zone_seconds = self._calculate_hr_zones_from_samples(hr_points, max_hr)
           parsed["hr_zone_1_seconds"] = zone_seconds[0]
           # ... 更新其他区间
   ```

2. **使用模拟心率曲线时**：
   - 当无法获取详细心率数据时，系统会根据平均心率和最大心率生成模拟曲线
   - 同样从模拟曲线计算心率区间

### 3. 在刷新心率数据时计算心率区间

修改了 `/api/workout/me/{workout_id}/refresh-hr` 接口，在刷新心率数据时：

```python
if hr_points:
    record.heart_rate_data = json.dumps(hr_points)
    
    # 如果心率区间数据为空，从心率采样计算
    total_zone_seconds = sum([...])
    if total_zone_seconds == 0:
        zone_seconds = sync_service._calculate_hr_zones_from_samples(hr_points, max_hr)
        record.hr_zone_1_seconds = zone_seconds[0]
        # ... 更新其他区间
```

### 4. 添加详细日志

在以下位置添加了日志，方便调试：

1. **`workout_sync.py`**：
   - 记录 Garmin API 返回的 `hrTimeInZones` 原始数据
   - 记录解析后的心率区间数据
   - 记录从心率采样计算的区间数据

2. **`post_workout_analysis.py`**：
   - 记录运动记录的心率区间数据
   - 警告没有心率数据或时长数据的情况

## 使用方法

### 对于新同步的数据

新同步的 Garmin 活动会自动计算心率区间（如果 Garmin 未提供）。

### 对于已有的数据

如果已有的运动记录心率区间为空，可以：

1. **前端操作**：在运动详情页点击"刷新心率数据"按钮
2. **后端脚本**：运行以下脚本批量修复：

```bash
cd backend
python scripts/fix_hr_zones.py [user_id]
```

### 调试工具

提供了调试脚本 `scripts/debug_hr_zones.py`，用于检查 Garmin API 返回的心率区间数据格式：

```bash
cd backend
python scripts/debug_hr_zones.py [user_id]
```

该脚本会：
- 获取用户最近的 5 个活动
- 显示 `hrTimeInZones` 字段的原始数据
- 显示所有包含 "hr"、"zone"、"heart" 的字段
- 显示活动详细信息中的心率相关数据

## 测试验证

### 1. 单元测试

可以添加单元测试验证心率区间计算逻辑：

```python
def test_calculate_hr_zones_from_samples():
    sync_service = WorkoutSyncService(...)
    
    # 模拟心率采样数据
    hr_samples = [
        {"time": 0, "hr": 120},    # Zone 2 (60-70%)
        {"time": 60, "hr": 140},   # Zone 3 (70-80%)
        {"time": 120, "hr": 160},  # Zone 4 (80-90%)
        {"time": 180, "hr": 180},  # Zone 5 (90-100%)
    ]
    
    max_hr = 200
    zones = sync_service._calculate_hr_zones_from_samples(hr_samples, max_hr)
    
    assert zones[1] > 0  # Zone 2 应该有时间
    assert zones[2] > 0  # Zone 3 应该有时间
    assert zones[3] > 0  # Zone 4 应该有时间
    assert zones[4] > 0  # Zone 5 应该有时间
```

### 2. 集成测试

1. 同步一个包含心率数据的 Garmin 活动
2. 检查数据库中的 `hr_zone_*_seconds` 字段是否有值
3. 访问前端页面，查看"❤️ 心率区间分析"是否正确显示

### 3. 前端验证

访问 https://health.westwetlandtech.com/workout，选择一个运动记录：

1. 点击"📊 科学分析"按钮
2. 查看"❤️ 心率区间分析"部分
3. 应该显示各区间的百分比和时长（不再是 0%）

## 技术细节

### 心率区间定义

根据运动科学标准，心率区间基于最大心率百分比定义：

| 区间 | 百分比 | 名称 | 训练效果 |
|------|--------|------|----------|
| Zone 1 | 50-60% | 恢复区 | 热身、恢复 |
| Zone 2 | 60-70% | 燃脂区 | 有氧基础、脂肪燃烧 |
| Zone 3 | 70-80% | 有氧区 | 有氧耐力 |
| Zone 4 | 80-90% | 乳酸阈值区 | 乳酸阈值训练 |
| Zone 5 | 90-100% | 最大心率区 | 无氧、高强度间歇 |

### 数据流

```
Garmin API
    ↓
hrTimeInZones (可能为空)
    ↓
[如果为空] → 获取心率时间序列
    ↓
_parse_heart_rate_samples()
    ↓
_calculate_hr_zones_from_samples()
    ↓
hr_zone_1_seconds ~ hr_zone_5_seconds
    ↓
数据库 WorkoutRecord
    ↓
PostWorkoutAnalysisService
    ↓
前端显示
```

## 注意事项

1. **最大心率**：计算使用运动记录的 `max_heart_rate`，如果不存在则使用默认值 180 bpm
2. **采样精度**：心率采样点间隔越小，计算越精确（当前为每 5-10 秒一个点）
3. **模拟数据**：对于无法获取详细心率数据的活动，会生成模拟曲线，准确度较低
4. **性能**：心率区间计算是线性复杂度 O(n)，对性能影响很小

## 后续优化

1. **用户最大心率配置**：允许用户在个人设置中配置自己的最大心率
2. **自适应区间**：根据用户的历史数据自动调整区间阈值
3. **批量修复工具**：提供管理后台批量修复历史数据的工具
4. **数据验证**：添加心率区间数据的合理性验证（总和应接近运动时长）

## 相关文件

- `backend/app/services/workout_sync.py` - 数据同步和心率区间计算
- `backend/app/services/post_workout_analysis.py` - 运动后分析服务
- `backend/app/api/workout.py` - 运动相关 API 接口
- `backend/app/models/daily_health.py` - WorkoutRecord 模型定义
- `backend/scripts/debug_hr_zones.py` - 调试工具
- `frontend/src/app/workout/page.tsx` - 前端运动页面

## 提交信息

```
fix(workout): 修复心率区间分析数据为空的问题

- 添加从心率采样数据计算心率区间的功能
- 在数据同步时自动计算心率区间（如果 Garmin 未提供）
- 在刷新心率数据时计算心率区间
- 添加详细日志方便调试
- 提供调试工具检查 Garmin API 数据格式

Closes #[issue_number]
```
