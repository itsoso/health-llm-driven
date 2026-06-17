# 补剂推荐字段名错误修复

**日期**: 2026-01-23  
**错误**: TypeError: Cannot read properties of undefined (reading 'sleep_quality')

## 🐛 问题描述

前端访问补剂推荐页面时报错：
```
TypeError: Cannot read properties of undefined (reading 'sleep_quality')
```

## 🔍 问题分析

### 后端日志错误

```
[ERROR] app.services.supplement_recommendation: [补剂推荐] 获取健康数据失败: 'GarminData' object has no attribute 'sleep_duration_hours'
[ERROR] app.services.supplement_recommendation: [补剂推荐] 获取饮食数据失败: type object 'DietRecord' has no attribute 'meal_date'
```

### 根本原因

代码中使用的字段名与数据库模型定义不匹配：

#### 1. GarminData 字段错误

**错误代码**:
```python
avg_sleep = sum(r.sleep_duration_hours or 0 for r in records) / len(records)
```

**实际模型**:
```python
class GarminData(Base):
    total_sleep_duration = Column(Integer)  # 总睡眠时长 (分钟)
```

**问题**: 
- 代码使用 `sleep_duration_hours`（不存在）
- 实际字段是 `total_sleep_duration`（单位：分钟）

#### 2. DietRecord 字段错误

**错误代码**:
```python
diet_records = db.query(DietRecord).filter(
    DietRecord.meal_date >= start_date,
    DietRecord.meal_date <= target_date
).all()
```

**实际模型**:
```python
class DietRecord(Base):
    record_date = Column(Date, nullable=False, index=True)
```

**问题**:
- 代码使用 `meal_date`（不存在）
- 实际字段是 `record_date`

## ✅ 修复方案

### 1. 修复 GarminData 字段

```python
# 修复前
avg_sleep = sum(r.sleep_duration_hours or 0 for r in records) / len(records)

# 修复后
# total_sleep_duration 是分钟，转换为小时
avg_sleep = sum((r.total_sleep_duration or 0) / 60 for r in records) / len(records)
```

**关键点**:
- 使用正确的字段名 `total_sleep_duration`
- 将分钟转换为小时（除以 60）

### 2. 修复 DietRecord 字段

```python
# 修复前
diet_records = db.query(DietRecord).filter(
    DietRecord.user_id == user_id,
    DietRecord.meal_date >= start_date,
    DietRecord.meal_date <= target_date
).all()

# 修复后
diet_records = db.query(DietRecord).filter(
    DietRecord.user_id == user_id,
    DietRecord.record_date >= start_date,
    DietRecord.record_date <= target_date
).all()
```

**关键点**:
- 使用正确的字段名 `record_date`

## 📋 修复步骤

### 1. 修改代码

**文件**: `backend/app/services/supplement_recommendation.py`

**修改位置**:
- 第 140 行：修复 `sleep_duration_hours`
- 第 212-213 行：修复 `meal_date`

### 2. 提交修复

```bash
git add backend/app/services/supplement_recommendation.py
git commit -m "fix(backend): 修复补剂推荐服务字段名错误"
git push
```

**提交**: a4c9b70

### 3. 部署到服务器

```bash
# SSH 到服务器
ssh root@health.westwetlandtech.com

# 拉取最新代码
cd /opt/health-app
git pull origin main

# 重启后端服务
systemctl restart health-backend

# 验证服务状态
systemctl status health-backend
```

## 🔍 验证方法

### 1. 检查后端日志

```bash
# 查看最新日志
journalctl -u health-backend -n 100 --no-pager | grep 'scientific-recommendation'

# 应该看到：
# - 没有 "has no attribute" 错误
# - 请求返回 200 OK
# - 推荐生成成功
```

### 2. 测试前端页面

访问: https://health.westwetlandtech.com/supplement-recommendation

**预期结果**:
- ✅ 页面正常加载
- ✅ 显示加载动画
- ✅ 成功获取推荐数据
- ✅ 显示健康分析（包括 sleep_quality）
- ✅ 显示推荐补剂列表

### 3. 检查 API 响应

```bash
# 使用有效的 token 测试 API
curl -X POST https://health.westwetlandtech.com/api/v1/supplements/scientific-recommendation \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**预期响应**:
```json
{
  "success": true,
  "rating": {
    "score": 85,
    "level": "优秀",
    "emoji": "🌟",
    "message": "您的补剂方案科学合理"
  },
  "analysis": {
    "sleep_quality": "良好",
    "stress_level": "中等",
    "exercise_intensity": "高",
    "nutrition_status": "均衡",
    "key_factors": [...]
  },
  "recommendations": [...],
  "timing_suggestions": {...},
  "precautions": [...]
}
```

## 📊 影响范围

### 受影响的功能
- ✅ 补剂科学推荐 API
- ✅ 健康数据分析
- ✅ 饮食数据查询

### 不受影响的功能
- ✅ 补剂列表查询
- ✅ 补剂打卡记录
- ✅ 补剂统计数据
- ✅ 其他页面功能

## 🎯 预防措施

### 1. 代码审查

在编写数据库查询代码时：
- ✅ 检查模型定义，确认字段名
- ✅ 注意字段的数据类型和单位
- ✅ 使用 IDE 的自动完成功能

### 2. 单元测试

为数据查询添加单元测试：
```python
def test_get_health_data():
    """测试健康数据查询"""
    data = service._get_health_data(db, user_id, target_date)
    assert data is not None
    assert "avg_sleep_hours" in data
    assert data["avg_sleep_hours"] > 0
```

### 3. 集成测试

测试完整的 API 流程：
```python
def test_supplement_recommendation_api():
    """测试补剂推荐 API"""
    response = client.post(
        "/api/v1/supplements/scientific-recommendation",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "analysis" in data
    assert "sleep_quality" in data["analysis"]
```

### 4. 错误日志监控

- ✅ 设置日志告警
- ✅ 监控 "has no attribute" 错误
- ✅ 及时发现和修复字段名错误

## 📚 相关模型字段参考

### GarminData 常用字段

```python
# 睡眠相关
total_sleep_duration      # 总睡眠时长 (分钟)
deep_sleep_duration       # 深度睡眠时长 (分钟)
rem_sleep_duration        # 快速眼动睡眠时长 (分钟)
sleep_score               # 睡眠分数 (0-100)

# 心率相关
resting_heart_rate        # 静息心率 (bpm)
avg_heart_rate            # 平均心率 (bpm)
hrv                       # 心率变异性 (ms)

# 压力相关
stress_level              # 压力水平 (0-100)
body_battery              # 身体电量 (0-100)

# 活动相关
steps                     # 步数
calories_burned           # 消耗卡路里
active_minutes            # 活动分钟数
```

### DietRecord 常用字段

```python
# 基本信息
record_date               # 记录日期
meal_type                 # 餐次（早餐/午餐/晚餐/加餐）
meal_time                 # 用餐时间

# 营养信息
calories                  # 卡路里
protein                   # 蛋白质 (g)
carbs                     # 碳水化合物 (g)
fat                       # 脂肪 (g)
```

## 🔗 相关文档

- [错误修复记录](./SUPPLEMENT_RECOMMENDATION_ERROR_FIX.md)
- [部署验证报告](./DEPLOYMENT_VERIFICATION_REPORT.md)
- [实现总结](./SUPPLEMENT_RECOMMENDATION_IMPLEMENTATION_SUMMARY.md)

## 📝 总结

### 问题根源
- 代码中使用的字段名与数据库模型定义不匹配
- 缺少字段名验证和单元测试

### 解决方案
- 修正所有字段名为正确的模型字段
- 添加单位转换（分钟 → 小时）

### 最终状态
- ✅ 后端 API 正常工作
- ✅ 前端可以正确显示数据
- ✅ 无字段名错误

---

**修复完成时间**: 2026-01-23 22:58 (UTC+8)  
**修复版本**: a4c9b70  
**状态**: ✅ 已解决
