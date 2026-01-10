# Apple Watch 适配指南

## 概述

Apple Watch 适配器支持从 iPhone 健康 App 导出的 XML 文件导入健康数据。由于 Apple 不提供公开的 Web API，我们采用文件导入的方式获取数据。

## 数据获取方式

### 1. 导出健康数据

在 iPhone 上操作：

1. 打开 **"健康"** App
2. 点击右上角 **头像**
3. 滚动到底部，点击 **"导出健康数据"**
4. 等待导出完成（可能需要几分钟）
5. 导出完成后，通过 AirDrop、邮件或其他方式将 XML 文件传输到电脑

### 2. 上传文件

在 Web 界面或小程序中：

1. 进入 **"设备管理"** → **"Apple Watch"**
2. 点击 **"导入健康数据"**
3. 选择导出的 XML 文件
4. 等待上传和解析完成

## 支持的数据类型

Apple Health 适配器支持以下数据类型：

### 活动数据
- ✅ 步数 (HKQuantityTypeIdentifierStepCount)
- ✅ 距离 (HKQuantityTypeIdentifierDistanceWalkingRunning)
- ✅ 活动卡路里 (HKQuantityTypeIdentifierActiveEnergyBurned)
- ✅ 基础代谢卡路里 (HKQuantityTypeIdentifierBasalEnergyBurned)
- ✅ 活动分钟数（估算）

### 心率数据
- ✅ 心率采样 (HKQuantityTypeIdentifierHeartRate)
- ✅ 静息心率（自动计算）
- ✅ 平均心率
- ✅ 最大心率
- ✅ 最小心率
- ✅ HRV (HKQuantityTypeIdentifierHeartRateVariabilitySDNN)

### 睡眠数据
- ✅ 睡眠时长 (HKCategoryTypeIdentifierSleepAnalysis)
- ✅ 入睡时间
- ✅ 起床时间
- ✅ 睡眠评分（估算）
- ⚠️ 深睡/REM/浅睡（估算，Apple Health 不直接提供）

### 其他数据
- ✅ 血氧饱和度 (HKQuantityTypeIdentifierOxygenSaturation)
- ✅ 呼吸频率 (HKQuantityTypeIdentifierRespiratoryRate)
- ✅ 运动记录 (HKWorkoutTypeIdentifier)

## API 端点

### 1. 导入健康数据

```http
POST /api/v1/devices/apple/import
Content-Type: multipart/form-data

file: <XML文件>
```

**响应：**
```json
{
  "success": true,
  "message": "导入成功：30 天数据已导入，0 天失败",
  "data_days": 30,
  "synced_days": 30,
  "failed_days": 0,
  "data_range": {
    "start": "2024-01-01",
    "end": "2024-01-30"
  }
}
```

### 2. 测试连接

```http
POST /api/v1/devices/apple/test-connection
```

**响应：**
```json
{
  "success": true,
  "message": "已导入 30 天的健康数据",
  "user_info": {
    "data_range": {
      "start": "2024-01-01",
      "end": "2024-01-30",
      "days": 30
    }
  }
}
```

### 3. 同步数据

```http
POST /api/v1/devices/apple/sync
Content-Type: application/json

{
  "days": 7
}
```

**响应：**
```json
{
  "success": true,
  "device": "apple",
  "synced_days": 7,
  "failed_days": 0,
  "message": "同步完成：成功 7 天，失败 0 天"
}
```

## 技术实现

### 数据解析流程

```
XML 文件
  ↓
解析 XML (xml.etree.ElementTree)
  ↓
提取 HealthKit 记录
  ↓
按日期聚合数据
  ↓
转换为 NormalizedHealthData
  ↓
保存到数据库
```

### 数据规范化

Apple Health 数据会被转换为统一的 `NormalizedHealthData` 格式，与其他设备（Garmin、华为）的数据格式一致，便于：

- 统一查询和分析
- 多设备数据合并
- AI 健康分析

### 数据存储

- **设备凭证**：存储在 `device_credentials` 表，`auth_type` 为 `file`
- **导入的数据**：存储在凭证的 `config` 字段（JSON 格式）
- **健康数据**：同步后保存到 `garmin_data` 表（兼容现有系统）

## 限制与注意事项

### 1. 数据更新

- ⚠️ **需要手动导出**：每次需要新数据时，需要重新从 iPhone 导出 XML 文件
- ⚠️ **不是实时同步**：数据是导出时的快照，不会自动更新

### 2. 数据精度

- ⚠️ **睡眠分段估算**：Apple Health 不直接提供深睡/REM/浅睡分段，我们使用估算算法
- ⚠️ **睡眠评分估算**：基于睡眠时长计算，不是 Apple Watch 的原始评分

### 3. 文件大小

- ⚠️ **文件可能很大**：长期使用 Apple Watch 的用户，导出文件可能达到几十MB
- ⚠️ **解析耗时**：大文件解析可能需要较长时间

### 4. 隐私安全

- ✅ **数据加密存储**：凭证和配置数据加密存储
- ✅ **用户隔离**：每个用户只能访问自己的数据
- ⚠️ **文件上传**：建议使用 HTTPS 传输，确保文件安全

## 未来改进方向

### 1. iOS App 直接读取

开发 iOS App，通过 HealthKit Framework 直接读取数据，无需导出文件：

```swift
import HealthKit

let healthStore = HKHealthStore()
let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!

healthStore.requestAuthorization(toShare: nil, read: [heartRateType]) { success, error in
    // 读取数据
}
```

### 2. 增量更新

- 记录上次导入的日期
- 只导入新数据，减少处理时间

### 3. 数据验证

- 验证 XML 文件格式
- 检查数据完整性
- 提供数据预览

### 4. 批量导入

- 支持多次导入
- 自动合并数据
- 处理数据冲突

## 使用示例

### Python 客户端示例

```python
import requests

# 上传文件
with open("export.xml", "rb") as f:
    files = {"file": ("export.xml", f, "application/xml")}
    response = requests.post(
        "https://health.westwetlandtech.com/api/v1/devices/apple/import",
        files=files,
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
    print(response.json())

# 同步数据
response = requests.post(
    "https://health.westwetlandtech.com/api/v1/devices/apple/sync",
    json={"days": 30},
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
print(response.json())
```

### JavaScript/TypeScript 示例

```typescript
// 上传文件
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/api/v1/devices/apple/import', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const result = await response.json();
console.log(result);
```

## 故障排查

### 问题：XML 解析失败

**原因**：
- 文件格式不正确
- 文件损坏
- 编码问题

**解决**：
- 确认文件是从 iPhone 健康 App 导出的原始 XML
- 检查文件是否完整
- 尝试重新导出

### 问题：导入后没有数据

**原因**：
- XML 文件中没有对应日期的数据
- 数据格式不匹配

**解决**：
- 检查导出文件是否包含健康数据
- 确认 Apple Watch 已同步数据到 iPhone

### 问题：同步失败

**原因**：
- 数据库连接问题
- 数据格式错误

**解决**：
- 查看服务器日志
- 检查数据库状态
- 重新导入文件

## 相关文档

- [多设备架构方案](./MULTI_DEVICE_ARCHITECTURE.md)
- [设备适配器基类](../backend/app/services/device_adapters/base.py)
- [Apple Health 适配器实现](../backend/app/services/device_adapters/apple.py)
