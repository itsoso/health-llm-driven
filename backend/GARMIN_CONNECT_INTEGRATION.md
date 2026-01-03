# Garmin Connect集成方案文档

## 概述

本方案使用社区库 `garminconnect` 来实现Garmin数据导入，无需官方API密钥，只需要Garmin Connect账号即可。

## 方案对比

### 方案1：官方Garmin API（当前实现）
- ✅ 官方支持
- ❌ 需要开发者账号
- ❌ 需要OAuth认证流程
- ❌ 申请和审核复杂

### 方案2：garminconnect社区库（推荐）
- ✅ 无需API密钥
- ✅ 只需Garmin Connect账号
- ✅ 实现简单
- ✅ 功能完整
- ⚠️ 非官方库，可能受Garmin政策变化影响

### 方案3：手动CSV导出导入
- ✅ 最稳定
- ❌ 需要手动操作
- ❌ 无法自动化

## 安装

### 1. 安装garminconnect库

```bash
cd backend
source venv/bin/activate
pip install garminconnect
```

或者添加到requirements.txt：

```bash
# 取消注释以下行
garminconnect>=0.2.0
```

### 2. 验证安装

```python
from garminconnect import Garmin
print("✅ garminconnect安装成功")
```

## 使用方法

### 方法1：通过API（推荐用于测试）

#### 测试登录

```bash
curl -X POST "http://localhost:8000/api/v1/garmin-connect/connect/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your_email@garmin.com",
    "password": "your_password"
  }'
```

#### 同步今日数据

```bash
curl -X POST "http://localhost:8000/api/v1/garmin-connect/connect/sync-today" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "email": "your_email@garmin.com",
    "password": "your_password"
  }'
```

#### 同步指定日期

```bash
curl -X POST "http://localhost:8000/api/v1/garmin-connect/connect/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "target_date": "2024-01-15",
    "email": "your_email@garmin.com",
    "password": "your_password"
  }'
```

#### 批量同步日期范围

```bash
curl -X POST "http://localhost:8000/api/v1/garmin-connect/connect/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "email": "your_email@garmin.com",
    "password": "your_password"
  }'
```

### 方法2：Python脚本（推荐用于生产）

创建脚本 `sync_garmin.py`:

```python
#!/usr/bin/env python3
"""Garmin数据同步脚本"""
import sys
from datetime import date, timedelta
from app.services.data_collection.garmin_connect import GarminConnectService
from app.database import SessionLocal
from app.models.user import User

def sync_garmin_data(email: str, password: str, user_id: int, days: int = 7):
    """同步最近N天的Garmin数据"""
    db = SessionLocal()
    try:
        service = GarminConnectService(email, password)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        result = service.sync_date_range(db, user_id, start_date, end_date)
        
        print(f"同步完成:")
        print(f"  成功: {result['success_count']} 条")
        print(f"  失败: {result['error_count']} 条")
        
        return result
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python sync_garmin.py <email> <password> <user_id> [days]")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    user_id = int(sys.argv[3])
    days = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    
    sync_garmin_data(email, password, user_id, days)
```

使用：

```bash
python sync_garmin.py your_email@garmin.com your_password 1 30
```

### 方法3：定时任务（自动化）

使用cron或系统定时任务：

```bash
# 编辑crontab
crontab -e

# 添加每天凌晨2点同步
0 2 * * * cd /path/to/backend && source venv/bin/activate && python sync_garmin.py email password user_id 1
```

## 安全建议

### ⚠️ 重要：密码安全

**不要**在前端直接传递密码！建议：

1. **使用环境变量**：
```bash
export GARMIN_EMAIL="your_email@garmin.com"
export GARMIN_PASSWORD="your_password"
```

2. **使用配置文件**（不要提交到git）：
```python
# config/garmin_credentials.py (添加到.gitignore)
GARMIN_EMAIL = "your_email@garmin.com"
GARMIN_PASSWORD = "your_password"
```

3. **使用密钥管理服务**：
   - AWS Secrets Manager
   - HashiCorp Vault
   - 环境变量管理工具

4. **实现OAuth流程**（未来）：
   - 用户在前端登录Garmin Connect
   - 获取session token
   - 后端使用token访问数据

## 数据字段映射

garminconnect库返回的数据会被自动映射到我们的数据模型：

| Garmin Connect字段 | 我们的字段 | 说明 |
|-------------------|-----------|------|
| sleepScore | sleep_score | 睡眠分数 |
| sleepTimeSeconds | total_sleep_duration | 总睡眠时长（秒转分钟） |
| deepSleepSeconds | deep_sleep_duration | 深度睡眠（秒转分钟） |
| remSleepSeconds | rem_sleep_duration | REM睡眠（秒转分钟） |
| averageHeartRate | avg_heart_rate | 平均心率 |
| restingHeartRate | resting_heart_rate | 静息心率 |
| bodyBatteryCharged | body_battery_charged | 身体电量充电值 |
| steps | steps | 步数 |
| calories | calories_burned | 消耗卡路里 |

## 故障排除

### 问题1：ImportError: No module named 'garminconnect'

**解决**：
```bash
pip install garminconnect
```

### 问题2：登录失败

**可能原因**：
- 账号或密码错误
- Garmin Connect要求二次验证
- 账号被锁定

**解决**：
- 检查账号密码
- 在浏览器登录Garmin Connect确认账号正常
- 如果启用二次验证，可能需要额外处理

### 问题3：获取数据为空

**可能原因**：
- 该日期没有数据
- Garmin Connect数据未同步
- API变化导致解析失败

**解决**：
- 检查Garmin Connect网站是否有该日期的数据
- 查看日志了解详细错误
- 更新garminconnect库到最新版本

### 问题4：请求频率过高

**解决**：
- 代码中已添加延迟（0.5秒）
- 可以增加延迟时间
- 避免短时间内大量请求

## 库信息

- **GitHub**: https://github.com/cyberjunky/python-garminconnect
- **PyPI**: https://pypi.org/project/garminconnect/
- **文档**: 查看GitHub README

## 注意事项

1. **非官方库**：garminconnect是社区维护的非官方库，可能受Garmin政策变化影响
2. **账号安全**：妥善保管Garmin Connect账号密码
3. **使用限制**：避免过于频繁的请求，可能触发Garmin的反爬虫机制
4. **数据准确性**：数据来自Garmin Connect，准确性取决于设备同步情况

## 未来改进

1. **Session管理**：实现session持久化，避免频繁登录
2. **OAuth支持**：如果Garmin提供官方OAuth，优先使用
3. **增量同步**：只同步缺失的数据，提高效率
4. **错误重试**：实现自动重试机制
5. **数据验证**：添加数据完整性检查

