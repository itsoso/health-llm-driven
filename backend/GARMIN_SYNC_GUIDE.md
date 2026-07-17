# Garmin数据同步完整指南

## 同步过去两年的数据

### 方法1：完整同步（推荐首次使用）

同步过去2年的所有数据：

```bash
cd backend
source venv/bin/activate
python scripts/sync_garmin_full.py itsoso@126.com <garmin-password> 1 2
```

**参数说明：**
- `itsoso@126.com` - Garmin Connect邮箱
- `<garmin-password>` - Garmin Connect密码
- `1` - user_id
- `2` - 同步过去2年的数据

**特点：**
- ✅ 显示详细进度
- ✅ 显示预计剩余时间
- ✅ 每10天显示一次统计
- ✅ 支持Ctrl+C中断（已同步的数据会保存）
- ⏱️ 预计耗时：约 730天 × 0.8秒 ≈ 10分钟

### 方法2：断点续传（推荐补充数据）

只同步缺失的日期：

```bash
python scripts/sync_garmin_resume.py itsoso@126.com <garmin-password> 1 2
```

**特点：**
- ✅ 自动检查已有数据
- ✅ 只同步缺失的日期
- ✅ 适合中断后继续
- ✅ 适合定期补充新数据

### 方法3：使用原始脚本（同步最近N天）

```bash
python scripts/sync_garmin.py itsoso@126.com <garmin-password> 1 730
```

同步最近730天（约2年）的数据。

## 性能优化建议

### 1. 分批同步

如果数据量很大，可以分批同步：

```bash
# 先同步最近1年
python scripts/sync_garmin_full.py email password 1 1

# 再同步前一年
# 需要修改脚本中的日期计算，或手动指定日期范围
```

### 2. 后台运行

使用 `nohup` 或 `screen` 在后台运行：

```bash
# 使用nohup
nohup python scripts/sync_garmin_full.py email password 1 2 > sync.log 2>&1 &

# 查看进度
tail -f sync.log
```

### 3. 使用screen（推荐）

```bash
# 启动screen会话
screen -S garmin_sync

# 运行同步
python scripts/sync_garmin_full.py email password 1 2

# 按 Ctrl+A 然后 D 分离会话
# 重新连接: screen -r garmin_sync
```

## 同步进度说明

同步过程中会显示：

```
[45.2%] 2024-06-15 - 预计剩余: 8分30秒 - ✅ 成功
```

- `[45.2%]` - 完成百分比
- `2024-06-15` - 当前同步的日期
- `预计剩余` - 预计剩余时间
- `✅ 成功` / `⚠️ 无数据` / `❌ 错误` - 同步状态

## 同步结果

同步完成后会显示：

```
============================================================
同步完成!
============================================================
✅ 成功: 650 条
⚠️  无数据: 50 天
❌ 错误: 30 天
⏱️  总耗时: 12分35秒
📈 平均速度: 58.2 天/分钟
```

## 常见问题

### Q: 同步需要多长时间？

A: 
- 每天数据约需 0.8-1 秒
- 2年（730天）约需 10-12 分钟
- 实际时间取决于网络速度和Garmin服务器响应

### Q: 可以中断吗？

A: 可以。按 `Ctrl+C` 中断，已同步的数据会保存。可以使用断点续传脚本继续同步剩余数据。

### Q: 如何知道哪些日期有数据？

A: 使用API检查：

```bash
curl "http://localhost:8000/api/v1/data-collection/garmin/sync-status/1?days=730"
```

### Q: 同步失败怎么办？

A: 
1. 检查网络连接
2. 确认Garmin账号正常
3. 使用断点续传脚本重试失败的日期
4. 查看错误日志了解具体原因

### Q: 如何只同步特定日期范围？

A: 可以修改脚本中的日期计算，或使用API：

```bash
curl -X POST "http://localhost:8000/api/v1/garmin-connect/connect/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "email": "your_email@garmin.com",
    "password": "your_password"
  }'
```

## 数据验证

同步完成后，验证数据：

```bash
# 查看同步状态
curl "http://localhost:8000/api/v1/data-collection/garmin/sync-status/1?days=730"

# 查看最近的数据
curl "http://localhost:8000/api/v1/daily-health/garmin/user/1?limit=10"

# 进行数据分析
curl "http://localhost:8000/api/v1/garmin-analysis/user/1/comprehensive?days=30"
```

## 定时同步

设置每天自动同步新数据：

```bash
# 编辑crontab
crontab -e

# 添加（每天凌晨3点同步昨日数据）
0 3 * * * cd /path/to/backend && source venv/bin/activate && python scripts/sync_garmin_resume.py email password user_id 1
```

## 注意事项

1. **账号安全**：不要在脚本中硬编码密码，使用环境变量
2. **请求频率**：代码中已添加延迟，避免请求过快
3. **数据完整性**：某些日期可能没有数据（设备未佩戴等），这是正常的
4. **网络稳定性**：确保网络稳定，避免频繁中断

