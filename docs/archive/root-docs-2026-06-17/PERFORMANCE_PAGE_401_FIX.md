# 性能监控页面 401 错误修复

## 问题描述

访问性能监控页面 (https://health.executor.life/admin/performance) 时，浏览器控制台报错：

```
/api/v1/performance/overview?hours=24:1 Failed to load resource: the server responded with a status of 401 ()
```

## 问题原因

### 根本原因：Token 加载时序问题

1. **组件初始化时 token 为空**
   - `useAuth()` 从 localStorage 异步加载 token
   - 组件首次渲染时，`token` 可能还是 `undefined`

2. **useEffect 立即触发 API 请求**
   ```typescript
   useEffect(() => {
     loadData();  // token 可能还未加载
   }, [timeRange, selectedPlatform]);
   ```

3. **API 请求缺少 Authorization header**
   ```typescript
   headers: { Authorization: `Bearer ${token}` }
   // 如果 token 是 undefined，实际发送的是：
   // Authorization: Bearer undefined
   ```

4. **后端返回 401 未授权**
   - 后端检测到无效的 token
   - 返回 401 Unauthorized

### 时序图

```
组件挂载
  ↓
useEffect 触发
  ↓
loadData() 执行
  ↓
API 请求发出 (token = undefined)
  ↓
后端返回 401
  ↓
[稍后] useAuth 加载完成
  ↓
token 更新
  ↓
但 useEffect 不会重新触发 ❌
```

## 解决方案

### 1. 添加 token 到 useEffect 依赖

```typescript
// 修改前
useEffect(() => {
  loadData();
}, [timeRange, selectedPlatform]);

// 修改后
useEffect(() => {
  // 等待 token 加载完成后再请求数据
  if (token) {
    loadData();
  }
}, [timeRange, selectedPlatform, token]);
```

**说明**:
- 将 `token` 添加到依赖数组
- 当 `token` 从 `undefined` 变为实际值时，`useEffect` 会重新执行
- 添加 `if (token)` 检查，避免 token 为空时发送请求

### 2. 在每个 API 请求前检查 token

```typescript
const loadOverview = async () => {
  // 添加 token 检查
  if (!token) {
    console.warn('Token 未加载，跳过请求');
    return;
  }
  
  try {
    const response = await fetch(
      `/api/v1/performance/overview?${params}`,
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    );
    
    if (response.ok) {
      const data = await response.json();
      setOverview(data);
    } else if (response.status === 401) {
      // 添加 401 错误处理
      console.error('未授权，请重新登录');
    }
  } catch (error) {
    console.error('加载性能概览失败:', error);
  }
};
```

**说明**:
- 每个 API 请求函数开头检查 `token`
- 如果 token 不存在，直接返回，避免无效请求
- 添加 401 错误的明确日志提示

### 3. 应用到所有 API 请求

修改了以下三个函数：
- `loadOverview()` - 性能概览
- `loadPagePerformance()` - 页面性能
- `loadAPIPerformance()` - API 性能

## 修复后的执行流程

```
组件挂载
  ↓
useEffect 触发
  ↓
检查 token (undefined)
  ↓
跳过 loadData() ✅
  ↓
[稍后] useAuth 加载完成
  ↓
token 更新
  ↓
useEffect 重新触发 (因为 token 在依赖中)
  ↓
检查 token (有效值)
  ↓
loadData() 执行
  ↓
API 请求发出 (带有效 token)
  ↓
后端返回 200 ✅
```

## 代码对比

### 修改文件
`frontend/src/app/admin/performance/page.tsx`

### 关键修改

#### useEffect 依赖
```diff
  useEffect(() => {
+   // 等待 token 加载完成后再请求数据
+   if (token) {
      loadData();
+   }
- }, [timeRange, selectedPlatform]);
+ }, [timeRange, selectedPlatform, token]);
```

#### API 请求函数
```diff
  const loadOverview = async () => {
+   if (!token) {
+     console.warn('Token 未加载，跳过请求');
+     return;
+   }
    
    try {
      // ... API 请求代码 ...
      
      if (response.ok) {
        const data = await response.json();
        setOverview(data);
+     } else if (response.status === 401) {
+       console.error('未授权，请重新登录');
      }
    } catch (error) {
      console.error('加载性能概览失败:', error);
    }
  };
```

## 测试验证

### 测试步骤

1. **清除浏览器缓存和 localStorage**
   ```javascript
   localStorage.clear();
   ```

2. **访问登录页面并登录**
   ```
   https://health.executor.life/login
   ```

3. **访问性能监控页面**
   ```
   https://health.executor.life/admin/performance
   ```

4. **检查浏览器控制台**
   - ✅ 不应该有 401 错误
   - ✅ 应该看到成功的 API 请求 (200)
   - ✅ 页面正常显示数据

5. **检查 Network 面板**
   ```
   Request Headers:
   Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc... (有效 token)
   
   Response:
   Status: 200 OK
   ```

### 预期结果

#### 修复前
```
❌ /api/v1/performance/overview?hours=24 401 (Unauthorized)
❌ /api/v1/performance/pages?platform=mini_program&hours=24 401 (Unauthorized)
❌ /api/v1/performance/apis?hours=24 401 (Unauthorized)
❌ 页面显示空数据或加载失败
```

#### 修复后
```
✅ /api/v1/performance/overview?hours=24 200 (OK)
✅ /api/v1/performance/pages?platform=mini_program&hours=24 200 (OK)
✅ /api/v1/performance/apis?hours=24 200 (OK)
✅ 页面正常显示性能数据
```

## 相关技术

### React useEffect 依赖数组

```typescript
useEffect(() => {
  // effect 代码
}, [dependency1, dependency2, ...]);
```

**规则**:
- 当依赖数组中的任何值发生变化时，effect 会重新执行
- 如果 effect 中使用了某个状态或 props，必须将其添加到依赖数组
- 空数组 `[]` 表示只在组件挂载时执行一次

### 异步状态加载

```typescript
const { token } = useAuth();  // token 初始值可能是 undefined

useEffect(() => {
  // 必须检查 token 是否已加载
  if (token) {
    // 使用 token
  }
}, [token]);  // token 作为依赖
```

### HTTP 401 错误处理

```typescript
const response = await fetch(url, {
  headers: { Authorization: `Bearer ${token}` }
});

if (response.status === 401) {
  // 未授权，可能需要重新登录
  console.error('未授权，请重新登录');
  // 可选：重定向到登录页
  // router.push('/login');
}
```

## 最佳实践

### 1. 认证状态管理

- ✅ 在 API 请求前检查 token 是否存在
- ✅ 将 token 添加到 useEffect 依赖
- ✅ 处理 401 错误，提示用户重新登录
- ✅ 考虑使用 token 刷新机制

### 2. 错误处理

```typescript
// 好的错误处理
if (response.status === 401) {
  console.error('未授权，请重新登录');
  // 可选：显示 toast 提示
  // 可选：重定向到登录页
}

// 不好的错误处理
if (!response.ok) {
  console.error('请求失败');  // 不够具体
}
```

### 3. 防御性编程

```typescript
// 在使用异步加载的值之前，总是检查它是否存在
if (!token) {
  return;  // 或者显示加载状态
}

// 然后再使用
const response = await fetch(url, {
  headers: { Authorization: `Bearer ${token}` }
});
```

## 部署记录

### 提交信息
```
commit d629d23
fix: 性能监控页面 401 未授权错误

问题：
- API 请求在 token 加载前就发出，导致 401 错误
- 缺少 token 检查和错误处理

修复：
1. useEffect 依赖添加 token，等待加载完成
2. 所有 API 请求前检查 token 是否存在
3. 添加 401 错误的明确日志提示

解决：/api/v1/performance/overview?hours=24 401 错误
```

### 部署时间
2026-01-24

### 部署状态
✅ 已部署到生产环境

## 其他可能需要类似修复的页面

以下页面如果也有类似的 token 依赖问题，需要检查并修复：

1. **管理中心首页** (`/admin`)
   - 检查是否有 API 请求依赖 token

2. **应用管理页面** (`/admin/applications`)
   - 检查 useEffect 依赖

3. **其他受保护的页面**
   - 所有需要认证的页面都应该检查

## 总结

通过添加 token 到 useEffect 依赖数组，并在 API 请求前检查 token 是否存在，成功解决了性能监控页面的 401 错误。这个修复确保了 API 请求只在用户认证完成后才发送，避免了无效的请求和错误提示。

**关键点**:
- ✅ 理解异步状态加载的时序
- ✅ 正确使用 useEffect 依赖数组
- ✅ 在使用异步值前进行检查
- ✅ 提供清晰的错误处理和日志

**修复时间**: 10分钟
**影响范围**: 性能监控页面
**问题严重性**: 中等（影响功能使用）
**修复效果**: ⭐⭐⭐⭐⭐

---

**相关文档**:
- PERFORMANCE_PAGE_FIX.md - 页面滚动修复
- PERFORMANCE_OPTIMIZATION_RECOMMENDATIONS.md - 性能优化建议
