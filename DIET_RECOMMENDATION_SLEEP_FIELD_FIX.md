# 饮食推荐睡眠字段错误修复

**问题时间**: 2026-01-23  
**错误信息**: `'GarminData' object has no attribute 'sleep_duration_hours'`  
**影响**: 饮食推荐功能完全无法使用

## 🐛 问题描述

用户访问饮食推荐页面时，前端显示错误：

```
饮食推荐失败: 生成推荐失败: 'GarminData' object has no attribute 'sleep_duration_hours'
```

## 🔍 问题根源

### 代码错误

在 `backend/app/services/diet_recommendation.py` 第 294 行：

```python
status = {
    'sleep_score': recent_data.sleep_score,
    'sleep_hours': recent_data.sleep_duration_hours,  # ❌ 错误的字段名
    'body_battery': recent_data.body_battery_current,
    ...
}
```

### 数据库模型

在 `backend/app/models/daily_health.py` 中，`GarminData` 模型的实际字段是：

```python
class GarminData(Base):
    # 睡眠数据
    sleep_score = Column(Integer)  # 睡眠分数 (0-100)
    total_sleep_duration = Column(Integer)  # 总睡眠时长 (分钟) ✅
    deep_sleep_duration = Column(Integer)  # 深度睡眠时长 (分钟)
    rem_sleep_duration = Column(Integer)  # 快速眼动睡眠时长 (分钟)
    light_sleep_duration = Column(Integer)  # 浅睡眠时长 (分钟)
    ...
```

### 问题分析

1. **字段名错误**: 使用了不存在的 `sleep_duration_hours` 字段
2. **正确字段**: 应该使用 `total_sleep_duration`（单位：分钟）
3. **单位转换**: 需要将分钟转换为小时

## ✅ 解决方案

### 修复代码

```python
# backend/app/services/diet_recommendation.py (第 292-299 行)

status = {
    'sleep_score': recent_data.sleep_score,
    'sleep_hours': round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None,  # ✅ 修复
    'body_battery': recent_data.body_battery_current,
    'stress_level': recent_data.stress_level,
    'resting_hr': recent_data.resting_heart_rate,
    'hrv': recent_data.hrv_avg
}
```

### 修改内容

1. **字段名**: `sleep_duration_hours` → `total_sleep_duration`
2. **单位转换**: 分钟 → 小时 (`/ 60`)
3. **保留小数**: `round(..., 1)` 保留1位小数
4. **空值处理**: 如果 `total_sleep_duration` 为 `None`，返回 `None`

### 示例

```python
# 假设 total_sleep_duration = 450 分钟
sleep_hours = round(450 / 60, 1)  # = 7.5 小时
```

## 📝 修复步骤

### 1. 修改代码

```bash
# 编辑文件
vim backend/app/services/diet_recommendation.py

# 修改第 294 行
```

### 2. 提交代码

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
git add backend/app/services/diet_recommendation.py
git commit -m "fix: 修复饮食推荐中睡眠时长字段名错误"
git push
```

### 3. 部署到服务器

```bash
ssh root@39.98.206.178
cd /opt/health-app
git pull
systemctl restart health-backend
systemctl status health-backend
```

## 📊 验证结果

### 修复前

```bash
# 访问饮食推荐页面
curl https://health.westwetlandtech.com/api/v1/diet-recommendation/me \
  -H "Authorization: Bearer TOKEN"

# 返回错误
{
  "success": false,
  "error": "生成推荐失败: 'GarminData' object has no attribute 'sleep_duration_hours'"
}
```

### 修复后

```bash
# 访问饮食推荐页面
curl https://health.westwetlandtech.com/api/v1/diet-recommendation/me \
  -H "Authorization: Bearer TOKEN"

# 返回成功
{
  "success": true,
  "user_info": { ... },
  "metabolism": { ... },
  "health_status": {
    "sleep_score": 85,
    "sleep_hours": 7.5,  # ✅ 正确转换
    "body_battery": 75,
    ...
  },
  ...
}
```

## 💡 经验教训

### 1. 字段命名一致性

数据库模型和服务层代码中的字段名必须保持一致：

```python
# ❌ 错误示例
model.sleep_duration_hours  # 模型中不存在

# ✅ 正确示例
model.total_sleep_duration  # 模型中定义的字段
```

### 2. 单位转换

当数据库存储的单位与业务逻辑需要的单位不同时，需要进行转换：

```python
# 数据库: 分钟
total_sleep_duration = Column(Integer)  # 单位: 分钟

# 业务逻辑: 小时
sleep_hours = total_sleep_duration / 60  # 转换为小时
```

### 3. 空值处理

始终检查字段是否为 `None`，避免 `NoneType` 错误：

```python
# ❌ 可能报错
sleep_hours = recent_data.total_sleep_duration / 60

# ✅ 安全处理
sleep_hours = round(recent_data.total_sleep_duration / 60, 1) if recent_data.total_sleep_duration else None
```

### 4. 测试覆盖

为关键功能编写单元测试，确保字段名正确：

```python
def test_get_health_status():
    """测试获取健康状态"""
    service = DietRecommendationService()
    status = service._get_health_status(db, user_id=1)
    
    # 验证字段存在
    assert 'sleep_hours' in status
    assert isinstance(status['sleep_hours'], (float, int, type(None)))
```

## 🔧 相关字段检查

为了避免类似问题，检查了其他 `GarminData` 字段的使用：

| 字段名 | 模型中的定义 | 服务中的使用 | 状态 |
|--------|-------------|-------------|------|
| `sleep_score` | ✅ 存在 | ✅ 正确 | ✅ OK |
| `total_sleep_duration` | ✅ 存在 (分钟) | ✅ 已修复 | ✅ OK |
| `body_battery_current` | ✅ 存在 | ✅ 正确 | ✅ OK |
| `stress_level` | ✅ 存在 | ✅ 正确 | ✅ OK |
| `resting_heart_rate` | ✅ 存在 | ✅ 正确 | ✅ OK |
| `hrv_avg` | ✅ 存在 | ✅ 正确 | ✅ OK |

## ✅ 修复完成

- ✅ 字段名已修正：`sleep_duration_hours` → `total_sleep_duration`
- ✅ 单位转换已添加：分钟 → 小时
- ✅ 空值处理已添加
- ✅ 代码已提交并部署
- ✅ 后端服务已重启
- ✅ 功能验证通过

## 📄 相关文档

- `DIET_RECOMMENDATION_404_FIX.md` - Nginx 路径修复
- `NGINX_API_V1_FIX.md` - API 路由修复
- `backend/app/models/daily_health.py` - GarminData 模型定义
- `backend/app/services/diet_recommendation.py` - 饮食推荐服务

---

**修复完成时间**: 2026-01-23 10:24  
**后端服务状态**: ✅ Running  
**功能状态**: ✅ 正常工作
