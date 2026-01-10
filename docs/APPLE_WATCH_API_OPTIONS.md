# Apple Watch 数据获取方案分析

## 现状分析

### ❌ Apple 不提供公开的 Web API

与华为、Garmin 不同，**Apple 没有提供类似 OAuth 2.0 的 Web API** 来直接获取 Apple Watch 的健康数据。

### Apple 提供的方案

#### 1. HealthKit Framework（仅限原生应用）

**限制**：
- ✅ 只能在 **iOS/macOS/watchOS** 原生应用中使用
- ❌ **不能通过 Web API** 访问
- ❌ 不能在服务器端直接调用

**使用场景**：
- 开发 iOS App，通过 HealthKit 读取数据
- 然后通过自己的 API 将数据传输到后端服务器

#### 2. Health Records API（医疗记录）

**限制**：
- 主要用于**医疗机构的电子病历**
- 不是日常健康数据（步数、心率、睡眠等）
- 需要医疗机构参与

#### 3. 数据导出（当前方案）

**优点**：
- ✅ 用户完全控制
- ✅ 隐私安全
- ✅ 无需开发 iOS App

**缺点**：
- ❌ 需要手动操作
- ❌ 不是实时同步

---

## 可行的解决方案

### 方案 1：开发 iOS App（推荐，长期方案）

#### 架构设计

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  iOS App    │     │  后端 API     │     │   Web 前端   │
│             │     │              │     │             │
│ HealthKit   │────>│  /api/v1/    │<────│  数据展示    │
│ 读取数据     │     │  health-data │     │             │
│             │     │              │     │             │
│ 定时同步     │     │  数据库存储   │     │             │
└─────────────┘     └──────────────┘     └─────────────┘
```

#### 实现步骤

1. **开发 iOS App**
   ```swift
   import HealthKit
   
   class HealthDataSync {
       let healthStore = HKHealthStore()
       
       func requestAuthorization() {
           let typesToRead: Set<HKObjectType> = [
               HKObjectType.quantityType(forIdentifier: .stepCount)!,
               HKObjectType.quantityType(forIdentifier: .heartRate)!,
               HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
               // ... 其他类型
           ]
           
           healthStore.requestAuthorization(toShare: nil, read: typesToRead) { success, error in
               if success {
                   self.syncData()
               }
           }
       }
       
       func syncData() {
           // 读取数据
           // 上传到后端 API
       }
   }
   ```

2. **后端 API 保持不变**
   - 使用现有的 `/api/v1/devices/apple/import` 端点
   - 或者新增 `/api/v1/devices/apple/sync` 端点接收 JSON 数据

3. **用户体验**
   - 用户在 iOS App 中授权
   - App 自动同步数据到服务器
   - Web 端实时显示最新数据

#### 优点
- ✅ 自动化同步，无需手动操作
- ✅ 实时数据更新
- ✅ 用户体验好

#### 缺点
- ❌ 需要开发 iOS App（需要 Apple Developer 账号，$99/年）
- ❌ 需要 App Store 审核
- ❌ 开发成本较高

---

### 方案 2：通过第三方健康平台（变通方案）

一些第三方健康平台可以同步 Apple Health 数据，然后从这些平台获取：

#### 可用的平台

1. **MyFitnessPal**
   - 支持 Apple Health 同步
   - 提供 API（需要申请）

2. **Strava**
   - 运动数据同步
   - 提供 API

3. **Google Fit**（如果用户同时使用）
   - 可以同步 Apple Health 数据
   - 提供 REST API

#### 实现流程

```
Apple Health → 第三方平台 → 我们的后端 API
```

#### 优点
- ✅ 无需开发 iOS App
- ✅ 可以自动化同步

#### 缺点
- ❌ 依赖第三方平台
- ❌ 数据可能不完整
- ❌ 需要用户额外授权第三方平台

---

### 方案 3：iCloud 数据同步（技术复杂）

#### 原理
- Apple Health 数据可能同步到 iCloud
- 通过 iCloud API 访问（需要用户授权）

#### 限制
- ⚠️ 技术实现复杂
- ⚠️ 需要用户开启 iCloud 同步
- ⚠️ 隐私和安全要求高
- ⚠️ Apple 可能限制访问

#### 不推荐
- 技术难度高
- 稳定性不确定
- 隐私风险

---

## 推荐方案对比

| 方案 | 开发成本 | 用户体验 | 自动化 | 推荐度 |
|------|---------|---------|--------|--------|
| **iOS App** | 高 | ⭐⭐⭐⭐⭐ | ✅ | ⭐⭐⭐⭐⭐ |
| **第三方平台** | 中 | ⭐⭐⭐ | ✅ | ⭐⭐⭐ |
| **文件导入**（当前） | 低 | ⭐⭐ | ❌ | ⭐⭐⭐ |
| **iCloud 同步** | 很高 | ⭐⭐⭐ | ✅ | ⭐ |

---

## 实施建议

### 短期（当前）
- ✅ **继续使用文件导入方案**
- ✅ 优化用户体验（更好的提示、进度显示）

### 中期（3-6个月）
- 📱 **开发 iOS App**
  - 使用 HealthKit 读取数据
  - 自动同步到后端
  - 提供更好的用户体验

### 长期（可选）
- 🔄 支持多个数据源
- 🔄 数据合并和去重
- 🔄 智能数据选择

---

## iOS App 开发指南

### 1. 项目设置

```swift
// Info.plist
<key>NSHealthShareUsageDescription</key>
<string>我们需要访问您的健康数据以提供个性化的健康分析</string>
<key>NSHealthUpdateUsageDescription</key>
<string>我们需要写入健康数据以记录您的活动</string>
```

### 2. 请求授权

```swift
import HealthKit

class HealthKitManager {
    private let healthStore = HKHealthStore()
    
    func requestAuthorization(completion: @escaping (Bool, Error?) -> Void) {
        guard HKHealthStore.isHealthDataAvailable() else {
            completion(false, NSError(domain: "HealthKit", code: -1))
            return
        }
        
        let typesToRead: Set<HKObjectType> = [
            HKObjectType.quantityType(forIdentifier: .stepCount)!,
            HKObjectType.quantityType(forIdentifier: .heartRate)!,
            HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
        ]
        
        healthStore.requestAuthorization(toShare: nil, read: typesToRead) { success, error in
            completion(success, error)
        }
    }
}
```

### 3. 读取数据

```swift
func fetchSteps(for date: Date, completion: @escaping (Double?) -> Void) {
    guard let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) else {
        completion(nil)
        return
    }
    
    let calendar = Calendar.current
    let startOfDay = calendar.startOfDay(for: date)
    let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay)!
    
    let predicate = HKQuery.predicateForSamples(
        withStart: startOfDay,
        end: endOfDay,
        options: .strictStartDate
    )
    
    let query = HKStatisticsQuery(
        quantityType: stepType,
        quantitySamplePredicate: predicate,
        options: .cumulativeSum
    ) { _, result, error in
        guard let result = result, let sum = result.sumQuantity() else {
            completion(nil)
            return
        }
        completion(sum.doubleValue(for: HKUnit.count()))
    }
    
    healthStore.execute(query)
}
```

### 4. 上传到后端

```swift
func syncToServer(data: HealthData, token: String) {
    let url = URL(string: "https://health.westwetlandtech.com/api/v1/devices/apple/sync")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    request.httpBody = try? encoder.encode(data)
    
    URLSession.shared.dataTask(with: request) { data, response, error in
        // 处理响应
    }.resume()
}
```

---

## 后端 API 扩展

如果需要支持 iOS App 直接上传数据，可以扩展 API：

```python
# backend/app/api/devices.py

@router.post("/apple/sync-data", summary="同步 Apple Health 数据（来自 iOS App）")
async def sync_apple_health_data(
    data: List[DailyHealthData],  # JSON 格式的健康数据
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    接收来自 iOS App 的健康数据
    
    与文件导入不同，这个接口接收结构化的 JSON 数据
    """
    # 处理数据...
    pass
```

---

## 总结

### 当前最佳方案
1. **短期**：继续使用文件导入（已实现）
2. **中期**：开发 iOS App 实现自动化同步
3. **长期**：考虑支持多个数据源

### 关键点
- ❌ **Apple 没有提供 Web API**，无法像华为那样直接 OAuth 绑定
- ✅ **HealthKit 只能在原生 iOS App 中使用**
- ✅ **文件导入是最简单可行的方案**
- ✅ **iOS App 是长期的最佳方案**

### 建议
如果用户量较大且对实时同步有需求，建议开发 iOS App。如果用户量较小或可以接受手动导入，当前的文件导入方案已经足够。
