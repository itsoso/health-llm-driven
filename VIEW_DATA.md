# 数据查看指南

## 查看同步后的Garmin数据

### 方法1：通过前端界面（推荐）

#### 启动前端服务

```bash
cd frontend
npm install  # 如果还没安装依赖
npm run dev
```

然后访问：**http://localhost:3000**

#### 查看Garmin数据

1. **首页** → 点击 **"Garmin数据"** 卡片
2. 或直接访问：**http://localhost:3000/garmin**

#### 功能说明

Garmin数据页面包含以下视图：

1. **原始数据**
   - 数据趋势图（睡眠分数、心率、步数）
   - 步数统计柱状图
   - 详细数据表格

2. **睡眠分析**
   - 平均睡眠分数
   - 睡眠时长分析
   - 深度睡眠和REM睡眠统计
   - 质量评估和建议

3. **心率分析**
   - 平均心率
   - 静息心率
   - 心率变异性(HRV)
   - 健康评估

4. **身体电量**
   - 充电/消耗值
   - 能量水平评估

5. **活动分析**
   - 步数统计
   - 卡路里消耗
   - 活动分钟数
   - 是否符合WHO建议

6. **综合分析**
   - 所有指标的汇总报告

#### 数据范围选择

在Garmin数据页面顶部，可以选择查看范围：
- 最近7天
- 最近30天
- 最近90天
- 最近180天
- 最近1年
- 最近2年

### 方法2：通过API（程序化访问）

#### 查看原始数据

```bash
# 查看最近30天的Garmin数据
curl "http://localhost:8000/api/v1/daily-health/garmin/user/1?start_date=2024-01-01&end_date=2024-12-31"
```

#### 查看睡眠分析

```bash
curl "http://localhost:8000/api/v1/garmin-analysis/user/1/sleep?days=30"
```

#### 查看心率分析

```bash
curl "http://localhost:8000/api/v1/garmin-analysis/user/1/heart-rate?days=30"
```

#### 查看综合分析

```bash
curl "http://localhost:8000/api/v1/garmin-analysis/user/1/comprehensive?days=30"
```

#### 查看同步状态

```bash
curl "http://localhost:8000/api/v1/data-collection/garmin/sync-status/1?days=730"
```

### 方法3：通过API文档（交互式）

1. 启动后端服务
2. 访问：**http://localhost:8000/docs**
3. 在Swagger UI中：
   - 找到 `/garmin-analysis` 相关端点
   - 点击 "Try it out"
   - 输入参数并执行
   - 查看返回的JSON数据

## 数据可视化

### 前端页面包含的图表

1. **趋势图**：显示睡眠分数、心率、步数等随时间的变化
2. **柱状图**：显示步数统计
3. **指标卡片**：显示关键健康指标
4. **数据表格**：显示详细的每日数据

### 自定义查看

如果需要自定义查看方式，可以：

1. **修改日期范围**：在页面顶部选择不同的天数
2. **切换标签页**：查看不同类型的分析
3. **导出数据**：通过API获取JSON数据，自行处理

## 数据统计

### 查看数据覆盖情况

```bash
curl "http://localhost:8000/api/v1/data-collection/garmin/sync-status/1?days=730"
```

返回示例：
```json
{
  "user_id": 1,
  "total_days": 730,
  "days_with_data": 650,
  "days_without_data": 80,
  "coverage_percentage": 89.0,
  "dates": [...]
}
```

## 快速访问链接

启动服务后，访问以下地址：

- **首页**: http://localhost:3000
- **Garmin数据页面**: http://localhost:3000/garmin
- **健康仪表盘**: http://localhost:3000/dashboard
- **API文档**: http://localhost:8000/docs

## 数据导出

### 导出为JSON

```bash
# 导出最近30天的数据
curl "http://localhost:8000/api/v1/daily-health/garmin/user/1?start_date=2024-01-01&end_date=2024-12-31" > garmin_data.json
```

### 导出为CSV（需要处理）

可以使用Python脚本处理JSON数据并转换为CSV。

## 常见问题

### Q: 为什么看不到数据？

A: 
1. 确认已同步数据：运行 `python scripts/list_users.py` 查看用户
2. 检查同步状态：使用sync-status API
3. 确认前端连接后端：检查浏览器控制台是否有错误

### Q: 图表不显示？

A:
1. 确认有数据：至少需要1条记录
2. 检查日期范围：确保选择的日期范围内有数据
3. 查看浏览器控制台：可能有JavaScript错误

### Q: 如何查看特定日期的数据？

A: 在Garmin数据页面的表格中查找，或使用API指定日期范围。

## 下一步

1. **数据分析**：使用 `/garmin-analysis` 端点进行深度分析
2. **健康建议**：使用 `/analysis` 端点获取AI生成的健康建议
3. **目标设置**：基于分析结果设置健康目标

