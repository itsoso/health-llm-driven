# 小程序补剂推荐 AttributeError 修复

## 问题描述

小程序补剂推荐页面点击"🤖 科学推荐"按钮后报错，无法生成推荐。

## 错误日志

```
2026-01-24 14:56:36 [ERROR] app.services.supplement_recommendation: 
[补剂推荐] 获取健康数据失败: 'GarminData' object has no attribute 'body_battery'

2026-01-24 14:56:36 [ERROR] app.services.supplement_recommendation: 
[补剂推荐] 生成失败: 'UserProfile' object has no attribute 'weight'

Traceback (most recent call last):
  File "/opt/health-app/backend/app/services/supplement_recommendation.py", line 70
    health_analysis = self._analyze_health_status(...)
  File "/opt/health-app/backend/app/services/supplement_recommendation.py", line 366
    if profile and profile.weight:
                   ^^^^^^^^^^^^^^
AttributeError: 'UserProfile' object has no attribute 'weight'
```

## 问题原因

### 1. UserProfile 字段名错误

**错误代码**:
```python
if profile and profile.weight:
    protein_per_kg = protein / profile.weight
```

**问题**: `UserProfile` 模型中的字段是 `current_weight_kg`，不是 `weight`

**正确字段**:
```python
# backend/app/models/user_profile.py
class UserProfile(Base):
    current_weight_kg = Column(Float, nullable=True)  # 当前体重(kg)
    target_weight_kg = Column(Float, nullable=True)   # 目标体重(kg)
```

### 2. GarminData 字段名错误

**错误代码**:
```python
"latest_body_battery": records[0].body_battery if records[0].body_battery else None
```

**问题**: `GarminData` 模型中没有 `body_battery` 字段，而是 `body_battery_current`

**正确字段**:
```python
# backend/app/models/daily_health.py
class GarminData(Base):
    body_battery_charged = Column(Integer)       # 身体电量充电值 (0-100)
    body_battery_drained = Column(Integer)       # 身体电量消耗值
    body_battery_most_charged = Column(Integer)  # 最高充电值
    body_battery_lowest = Column(Integer)        # 最低值
    body_battery_current = Column(Integer)       # 当前实时电量 ✅
```

## 解决方案

### 修改文件
`backend/app/services/supplement_recommendation.py`

### 修改 1: 修复 body_battery 字段

```python
# 修改前 (第 152 行)
"latest_body_battery": records[0].body_battery if records[0].body_battery else None

# 修改后
"latest_body_battery": records[0].body_battery_current if records[0].body_battery_current else None
```

### 修改 2: 修复 weight 字段

```python
# 修改前 (第 366-367 行)
if profile and profile.weight:
    protein_per_kg = protein / profile.weight

# 修改后
if profile and profile.current_weight_kg:
    protein_per_kg = protein / profile.current_weight_kg
```

## 代码对比

### 完整修改对比

```diff
# supplement_recommendation.py 第 149-154 行
                "avg_stress_level": round(avg_stress, 1),
                "avg_resting_hr": round(avg_rhr, 0),
                "latest_sleep_score": records[0].sleep_score if records[0].sleep_score else None,
-               "latest_body_battery": records[0].body_battery if records[0].body_battery else None,
+               "latest_body_battery": records[0].body_battery_current if records[0].body_battery_current else None,
                "data_count": len(records)
            }

# supplement_recommendation.py 第 363-367 行
        # 4. 营养状况分析
        if diet_data:
            protein = diet_data.get("avg_daily_protein", 0)
-           if profile and profile.weight:
-               protein_per_kg = protein / profile.weight
+           if profile and profile.current_weight_kg:
+               protein_per_kg = protein / profile.current_weight_kg
```

## 测试验证

### 测试步骤

1. **打开小程序补剂页面**
   ```
   小程序 → 补剂 tab
   ```

2. **点击"🤖 科学推荐"按钮**
   - 应该显示"分析中..."
   - 不应该报错

3. **检查推荐结果**
   - 应该显示推荐弹窗
   - 包含健康分析、推荐补剂、服用时间等信息

4. **查看后端日志**
   ```bash
   ssh root@health.westwetlandtech.com
   journalctl -u health-backend -f | grep "补剂推荐"
   ```

### 预期结果

#### 修复前
```
❌ [补剂推荐] 获取健康数据失败: 'GarminData' object has no attribute 'body_battery'
❌ [补剂推荐] 生成失败: 'UserProfile' object has no attribute 'weight'
❌ 小程序显示"生成推荐失败"
```

#### 修复后
```
✅ [补剂推荐] 开始为用户 3 生成推荐
✅ [补剂推荐] 健康数据获取成功
✅ [补剂推荐] 生成成功 - success=True
✅ 小程序显示推荐弹窗
```

## 根本原因分析

### 为什么会出现这个问题？

1. **字段命名不一致**
   - 代码中使用了简化的字段名 `weight`
   - 但数据库模型使用了更明确的字段名 `current_weight_kg`

2. **字段结构变化**
   - `body_battery` 被拆分为多个字段：
     - `body_battery_current` (当前值)
     - `body_battery_charged` (充电值)
     - `body_battery_drained` (消耗值)
     - 等

3. **缺少类型检查**
   - Python 的动态类型特性导致在运行时才发现字段不存在
   - 没有使用 IDE 的类型提示或静态类型检查

## 预防措施

### 1. 使用类型提示

```python
from typing import Optional
from app.models.user_profile import UserProfile

def _analyze_health_status(
    self,
    profile: Optional[UserProfile],  # 明确类型
    garmin_data: Optional[Dict[str, Any]],
    diet_data: Optional[Dict[str, Any]],
    supplement_status: Dict[str, Any]
) -> Dict[str, Any]:
    # IDE 会提示可用字段
    if profile and profile.current_weight_kg:  # ✅ 自动补全
        ...
```

### 2. 添加字段验证

```python
# 在访问字段前检查是否存在
if hasattr(profile, 'current_weight_kg') and profile.current_weight_kg:
    protein_per_kg = protein / profile.current_weight_kg
else:
    logger.warning("用户体重数据缺失")
```

### 3. 使用 Pydantic 模型

```python
from pydantic import BaseModel

class HealthAnalysisInput(BaseModel):
    current_weight_kg: Optional[float] = None
    body_battery_current: Optional[int] = None
    
    class Config:
        from_attributes = True

# 使用时会自动验证字段
input_data = HealthAnalysisInput.from_orm(profile)
```

### 4. 添加单元测试

```python
# tests/test_supplement_recommendation.py
def test_analyze_health_status_with_weight():
    """测试有体重数据的健康分析"""
    profile = UserProfile(current_weight_kg=70.0)
    service = SupplementRecommendationService()
    
    result = service._analyze_health_status(
        profile=profile,
        garmin_data=None,
        diet_data={"avg_daily_protein": 80},
        supplement_status={}
    )
    
    assert result["nutrition_status"] is not None
```

## 相关模型字段参考

### UserProfile 常用字段

```python
# 身体数据
current_weight_kg: float      # 当前体重(kg) ✅
target_weight_kg: float       # 目标体重(kg)
height_cm: float              # 身高(cm)
body_fat_percentage: float    # 体脂率(%)
muscle_mass_kg: float         # 肌肉量(kg)

# 基本信息
gender: str                   # 性别
birth_date: date              # 出生日期
blood_type: str               # 血型
```

### GarminData 身体电量字段

```python
# 身体电量相关字段
body_battery_current: int          # 当前实时电量 ✅
body_battery_charged: int          # 充电值
body_battery_drained: int          # 消耗值
body_battery_most_charged: int     # 最高充电值
body_battery_lowest: int           # 最低值
```

### GarminData 其他常用字段

```python
# 心率数据
resting_heart_rate: int       # 静息心率 ✅
avg_heart_rate: int           # 平均心率
max_heart_rate: int           # 最大心率

# 睡眠数据
sleep_score: int              # 睡眠分数 ✅
total_sleep_duration: int     # 总睡眠时长(分钟)
deep_sleep_duration: int      # 深度睡眠时长

# 压力数据
stress_level: int             # 压力水平 ✅
```

## 部署记录

### 提交信息
```
commit 12a1720
fix: 修复小程序补剂推荐 AttributeError

问题：
1. 'UserProfile' object has no attribute 'weight'
2. 'GarminData' object has no attribute 'body_battery'

修复：
1. profile.weight → profile.current_weight_kg
2. body_battery → body_battery_current

错误日志：
- AttributeError at supplement_recommendation.py:366
- AttributeError at supplement_recommendation.py:152

影响：小程序补剂推荐功能无法使用
```

### 部署时间
2026-01-24 15:26:57

### 部署状态
✅ 已部署到生产环境

### 验证命令
```bash
# 查看后端日志
ssh root@health.westwetlandtech.com
journalctl -u health-backend -f | grep "补剂推荐"

# 测试 API
curl -X POST https://health.executor.life/api/v1/supplements/scientific-recommendation \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"target_date": "2026-01-24"}'
```

## 总结

通过修复两个字段名错误，成功解决了小程序补剂推荐功能的 AttributeError 问题。这个问题提醒我们：

1. **字段命名要一致** - 避免使用简化名称
2. **使用类型提示** - 让 IDE 帮助检查字段
3. **添加单元测试** - 及早发现字段错误
4. **完善错误处理** - 提供更友好的错误提示

**修复时间**: 15分钟
**影响范围**: 小程序补剂推荐功能
**问题严重性**: 高（功能完全无法使用）
**修复效果**: ⭐⭐⭐⭐⭐

---

**相关文档**:
- SUPPLEMENT_MIGRATION_COMPLETE.md - 补剂功能迁移文档
- SUPPLEMENT_TEST_GUIDE.md - 补剂功能测试指南
