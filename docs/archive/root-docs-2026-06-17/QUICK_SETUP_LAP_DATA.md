# 快速部署计圈功能

## 1. 运行数据库迁移

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
sqlite3 health.db < ../scripts/migrations/20260121_01_add_lap_data_to_workout.sql
```

验证迁移成功：
```bash
sqlite3 health.db "PRAGMA table_info(workout_records);" | grep lap_data
```

应该看到输出：
```
22|lap_data|TEXT|0||0
```

## 2. 重启后端服务

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
# 停止现有服务
pkill -f "python.*main.py"

# 启动服务
./start.sh
```

## 3. 测试功能

### 3.1 测试API端点

```bash
# 获取运动详情（检查是否返回lap_data字段）
curl -X GET "http://localhost:8000/workout/me/YOUR_WORKOUT_ID" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 刷新计圈数据
curl -X POST "http://localhost:8000/workout/me/YOUR_WORKOUT_ID/refresh-laps" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3.2 测试前端

1. 重新编译小程序：
```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

2. 打开微信开发者工具，刷新项目

3. 进入任意运动详情页，应该看到三个Tab：
   - 统计信息
   - 计圈
   - 区间用时

## 4. 同步历史数据（可选）

如果需要为历史运动记录补充计圈数据：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/backend
python -c "
from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord
from app.services.workout_sync import WorkoutSyncService
from app.services.auth import GarminCredentialService
import asyncio
import json

db = SessionLocal()
user_id = 1  # 替换为你的用户ID

# 获取Garmin凭证
cred_service = GarminCredentialService()
credentials = cred_service.get_decrypted_credentials(db, user_id)

if credentials:
    sync_service = WorkoutSyncService(
        email=credentials['email'],
        password=credentials['password'],
        is_cn=credentials.get('is_cn', False),
        user_id=user_id
    )
    
    # 获取所有Garmin来源且没有lap_data的记录
    records = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == user_id,
        WorkoutRecord.source == 'garmin',
        WorkoutRecord.external_id.isnot(None),
        WorkoutRecord.lap_data.is_(None)
    ).limit(50).all()
    
    print(f'找到 {len(records)} 条需要补充计圈数据的记录')
    
    async def refresh_laps():
        for record in records:
            try:
                details = await sync_service.get_activity_details(int(record.external_id))
                if details and details.get('lap_data'):
                    lap_points = sync_service._parse_lap_data(details['lap_data'])
                    if lap_points:
                        record.lap_data = json.dumps(lap_points)
                        print(f'✓ 运动 {record.id} 补充了 {len(lap_points)} 圈数据')
            except Exception as e:
                print(f'✗ 运动 {record.id} 失败: {e}')
        db.commit()
    
    asyncio.run(refresh_laps())
else:
    print('未找到Garmin凭证')

db.close()
"
```

## 5. 验证结果

### 5.1 检查数据库

```bash
sqlite3 health.db "SELECT id, workout_name, lap_data IS NOT NULL as has_laps FROM workout_records WHERE source='garmin' LIMIT 10;"
```

### 5.2 检查日志

```bash
tail -f backend/backend.log | grep -i "lap"
```

应该看到类似日志：
```
INFO - 用户 1 刷新运动 123 计圈数据: 10 圈
DEBUG - 解析计圈数据得到 10 圈
```

## 6. 常见问题

### Q1: 迁移失败 "table workout_records has no column named lap_data"

**解决**: 确认你在正确的数据库文件上执行迁移
```bash
ls -la backend/health.db
sqlite3 backend/health.db "SELECT name FROM sqlite_master WHERE type='table';"
```

### Q2: 前端看不到Tab

**解决**: 清除小程序缓存
1. 微信开发者工具 → 清除缓存 → 清除全部
2. 重新编译项目

### Q3: 计圈数据为空

**可能原因**:
- 该运动是室内运动，Garmin未记录分段
- 需要手动刷新数据

**解决**: 在运动详情页点击"刷新"按钮，或调用 `/refresh-laps` API

## 7. 回滚（如果需要）

```bash
sqlite3 backend/health.db "ALTER TABLE workout_records DROP COLUMN lap_data;"
```

## 完成！

现在你的运动详情页应该已经支持计圈和区间用时功能了。

查看完整文档: `LAP_DATA_IMPLEMENTATION.md`
