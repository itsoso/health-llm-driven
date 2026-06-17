# 饮食推荐 GarminData 字段错误完整修复

**问题时间**: 2026-01-23  
**影响**: 饮食推荐功能完全无法使用  
**修复状态**: ✅ 已完成

## 🐛 问题汇总

在实现饮食推荐功能时，`_get_health_status` 方法中使用了多个错误的 `GarminData` 字段名，导致功能完全无法使用。

### 错误 1: sleep_duration_hours

**错误信息**: `'GarminData' object has no attribute 'sleep_duration_hours'`

```python
# ❌ 错误代码
'sleep_hours': recent_data.sleep_duration_hours
```

**问题**: 
- 字段名错误
- 缺少单位转换（数据库存储的是分钟，需要转换为小时）

### 错误 2: hrv_avg

**错误信息**: `'GarminData' object has no attribute 'hrv_avg'`

```python
# ❌ 错误代码
'hrv': recent_data.hrv_avg
```

**问题**: 字段名错误

## 📊 GarminData 模型字段对照表

### 睡眠相关字段

| 错误字段名 | 正确字段名 | 类型 | 单位 | 说明 |
|-----------|-----------|------|------|------|
| ❌ `sleep_duration_hours` | ✅ `total_sleep_duration` | Integer | 分钟 | 总睡眠时长 |
| - | `deep_sleep_duration` | Integer | 分钟 | 深度睡眠时长 |
| - | `rem_sleep_duration` | Integer | 分钟 | 快速眼动睡眠时长 |
| - | `light_sleep_duration` | Integer | 分钟 | 浅睡眠时长 |
| - | `awake_duration` | Integer | 分钟 | 清醒时长 |
| - | `nap_duration` | Integer | 分钟 | 小睡时长 |
| ✅ `sleep_score` | `sleep_score` | Integer | 0-100 | 睡眠分数 |

### 心率变异性 (HRV) 相关字段

| 错误字段名 | 正确字段名 | 类型 | 单位 | 说明 |
|-----------|-----------|------|------|------|
| ❌ `hrv_avg` | ✅ `hrv` | Float | ms | 当日心率变异性 |
| - | `hrv_7day_avg` | Float | ms | 7天平均HRV |
| - | `hrv_status` | String | - | HRV状态 (balanced/unbalanced/low) |

### 其他健康指标（已正确）

| 字段名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| ✅ `body_battery_current` | Integer | 0-100 | 当前身体电量 |
| ✅ `stress_level` | Integer | 0-100 | 压力水平 |
| ✅ `resting_heart_rate` | Integer | bpm | 静息心率 |

## ✅ 完整修复方案

### 修复后的代码

```python
# backend/app/services/diet_recommendation.py

def _get_health_status(self, db: Session, user_id: int) -> Dict[str, Any]:
    """
    获取用户最近的健康状态
    """
    try:
        today = get_china_now().date()
        recent_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == today
        ).first()
        
        if not recent_data:
            logger.info(f"[饮食推荐] 今日无 Garmin 健康数据")
            return {}
        
        status = {
            'sleep_score': recent_data.sleep_score,
            # ✅ 修复 1: 使用正确字段名并转换单位
            'sleep_hours': round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None,
            'body_battery': recent_data.body_battery_current,
            'stress_level': recent_data.stress_level,
            'resting_hr': recent_data.resting_heart_rate,
            # ✅ 修复 2: 使用正确字段名
            'hrv': recent_data.hrv
        }
        
        logger.info(f"[饮食推荐] 健康状态: 睡眠{status['sleep_score']}/100, 身体电量{status['body_battery']}, 压力{status['stress_level']}")
        return status
        
    except Exception as e:
        logger.error(f"[饮食推荐] 获取健康状态失败: {str(e)}", exc_info=True)
        return {}
```

### 修复要点

#### 1. 睡眠时长字段

```python
# ❌ 错误
'sleep_hours': recent_data.sleep_duration_hours

# ✅ 正确
'sleep_hours': round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None
```

**改进**:
- 使用正确的字段名 `total_sleep_duration`
- 单位转换：分钟 → 小时 (`/ 60`)
- 保留1位小数 (`round(..., 1)`)
- 空值安全处理 (`if ... else None`)

#### 2. HRV 字段

```python
# ❌ 错误
'hrv': recent_data.hrv_avg

# ✅ 正确
'hrv': recent_data.hrv
```

**说明**:
- 使用当日 HRV 值 (`hrv`)
- 如果需要平均值，可以使用 `hrv_7day_avg`

## 📝 字段验证结果

### 验证脚本

```python
from app.models.daily_health import GarminData
from sqlalchemy import inspect

# 获取所有列
mapper = inspect(GarminData)
columns = [c.key for c in mapper.columns]

# 验证使用的字段
used_fields = [
    'sleep_score',
    'total_sleep_duration',
    'body_battery_current',
    'stress_level',
    'resting_heart_rate',
    'hrv'
]

for field in used_fields:
    status = '✅' if field in columns else '❌'
    print(f'{status} {field}')
```

### 验证结果

```
✅ sleep_score
✅ total_sleep_duration
✅ body_battery_current
✅ stress_level
✅ resting_heart_rate
✅ hrv
```

**所有字段验证通过！** ✅

## 🔧 修复步骤

### 1. 修复睡眠字段（第一次）

```bash
# 修改代码
vim backend/app/services/diet_recommendation.py

# 提交
git add backend/app/services/diet_recommendation.py
git commit -m "fix: 修复饮食推荐中睡眠时长字段名错误"
git push

# 部署
ssh root@39.98.206.178
cd /opt/health-app && git pull && systemctl restart health-backend
```

### 2. 修复 HRV 字段（第二次）

```bash
# 修改代码
vim backend/app/services/diet_recommendation.py

# 提交
git add backend/app/services/diet_recommendation.py
git commit -m "fix: 修复饮食推荐中 HRV 字段名错误 (hrv_avg -> hrv)"
git push

# 部署
ssh root@39.98.206.178
cd /opt/health-app && git pull && systemctl restart health-backend
```

## 📊 测试结果

### 修复前

```bash
curl https://health.westwetlandtech.com/api/v1/diet-recommendation/me \
  -H "Authorization: Bearer TOKEN"

# 返回错误
{
  "success": false,
  "error": "生成推荐失败: 'GarminData' object has no attribute 'sleep_duration_hours'"
}

# 或
{
  "success": false,
  "error": "生成推荐失败: 'GarminData' object has no attribute 'hrv_avg'"
}
```

### 修复后

```bash
curl https://health.westwetlandtech.com/api/v1/diet-recommendation/me \
  -H "Authorization: Bearer TOKEN"

# 返回成功
{
  "success": true,
  "user_info": {
    "age": 41,
    "gender": "male",
    "height_cm": 173.0,
    "current_weight_kg": 75.6,
    "target_weight_kg": 70.0,
    "weight_goal": "lose",
    "diet_preference": null,
    "activity_level": "very_active"
  },
  "metabolism": {
    "bmr": 1637,
    "tdee": 3377,
    "avg_exercise_calories": 267
  },
  "daily_target": {
    "calories": 2877,
    "protein_g": 179.8,
    "carbs_g": 323.6,
    "fat_g": 95.9
  },
  "today_intake": {
    "calories": 250.0,
    "protein_g": 7.0,
    "carbs_g": 40.0,
    "fat_g": 6.0,
    "meals_count": 1
  },
  "remaining": {
    "calories": 2627,
    "protein_g": 172.8,
    "carbs_g": 283.6,
    "fat_g": 89.9
  },
  "progress": {
    "calories_percent": 8.7,
    "protein_percent": 3.9,
    "carbs_percent": 12.4,
    "fat_percent": 6.3
  },
  "health_status": {
    "sleep_score": 85,
    "sleep_hours": 7.5,  # ✅ 正确转换
    "body_battery": 75,
    "stress_level": 30,
    "resting_hr": 55,
    "hrv": 45.2  # ✅ 正确字段
  },
  "warnings": [
    "今日热量摄入不足，建议增加营养摄入"
  ],
  "tips": [
    "您的运动量较大，建议适当增加蛋白质摄入",
    "睡眠质量良好，继续保持"
  ],
  "food_recommendations": [
    {
      "category": "优质蛋白质",
      "foods": ["鸡胸肉", "鱼肉", "豆腐"],
      "reason": "高蛋白低脂肪，适合减脂期",
      "priority": "high"
    }
  ],
  "scientific_insights": {
    "available": false,
    "reason": "RAG pipeline 暂未实现"
  }
}
```

## 💡 经验教训

### 1. 字段命名规范

在使用 ORM 模型时，必须使用模型中定义的确切字段名：

```python
# ❌ 错误：猜测字段名
model.sleep_duration_hours
model.hrv_avg

# ✅ 正确：使用模型定义的字段名
model.total_sleep_duration
model.hrv
```

### 2. 单位转换

数据库存储单位与业务逻辑单位不同时，需要进行转换：

```python
# 数据库: 分钟
total_sleep_duration = Column(Integer)

# 业务逻辑: 小时
sleep_hours = round(total_sleep_duration / 60, 1)
```

### 3. 空值安全

始终处理可能为 `None` 的字段：

```python
# ❌ 可能报错
sleep_hours = recent_data.total_sleep_duration / 60

# ✅ 安全处理
sleep_hours = round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None
```

### 4. 字段验证

在使用模型字段前，先验证字段是否存在：

```python
from sqlalchemy import inspect

mapper = inspect(GarminData)
columns = [c.key for c in mapper.columns]

# 验证字段存在
assert 'total_sleep_duration' in columns
assert 'hrv' in columns
```

### 5. 单元测试

为关键功能编写单元测试：

```python
def test_get_health_status():
    """测试获取健康状态"""
    service = DietRecommendationService()
    status = service._get_health_status(db, user_id=1)
    
    # 验证返回的字段
    assert 'sleep_hours' in status
    assert 'hrv' in status
    
    # 验证数据类型
    if status['sleep_hours'] is not None:
        assert isinstance(status['sleep_hours'], float)
    if status['hrv'] is not None:
        assert isinstance(status['hrv'], (int, float))
```

## ✅ 修复完成

### 修复内容

- ✅ 修复睡眠时长字段：`sleep_duration_hours` → `total_sleep_duration`
- ✅ 添加单位转换：分钟 → 小时
- ✅ 修复 HRV 字段：`hrv_avg` → `hrv`
- ✅ 添加空值安全处理
- ✅ 验证所有字段正确性

### 部署状态

- ✅ 代码已提交到 Git
- ✅ 后端服务已重启
- ✅ 功能测试通过

### 验证清单

- ✅ API 返回 200 状态码
- ✅ `success: true`
- ✅ `health_status` 包含所有字段
- ✅ `sleep_hours` 正确转换为小时
- ✅ `hrv` 正确获取
- ✅ 无 AttributeError 错误

## 📄 相关文档

- `backend/app/models/daily_health.py` - GarminData 模型定义
- `backend/app/services/diet_recommendation.py` - 饮食推荐服务
- `DIET_RECOMMENDATION_404_FIX.md` - Nginx 路径修复
- `NGINX_API_V1_FIX.md` - API 路由修复

---

**修复完成时间**: 2026-01-23 10:26  
**后端服务状态**: ✅ Running  
**功能状态**: ✅ 完全正常
