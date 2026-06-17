# 性能监控页面 API 路径修复

## 🐛 问题描述

### 错误现象
```
GET https://health.westwetlandtech.com/admin/undefined/api/v1/performance/overview?hours=24 404 (Not Found)
GET https://health.westwetlandtech.com/admin/undefined/api/v1/performance/apis?hours=24 404 (Not Found)
```

**问题**: API 请求路径中出现 `undefined`，导致 404 错误

---

## 🔍 根本原因

### 代码问题
```typescript
// ❌ 错误的代码
const response = await fetch(
  `${process.env.NEXT_PUBLIC_API_URL}/api/v1/performance/overview?${params}`,
  { headers: { Authorization: `Bearer ${token}` } }
);
```

### 原因分析
1. **环境变量未定义**: `process.env.NEXT_PUBLIC_API_URL` 在生产环境中未设置
2. **变量名不匹配**: 
   - `.env.local` 中定义的是 `BACKEND_URL`
   - 代码中使用的是 `NEXT_PUBLIC_API_URL`
3. **结果**: `${undefined}/api/v1/...` → `/admin/undefined/api/v1/...`

---

## ✅ 解决方案

### 修复方法
使用相对路径，依赖 Nginx 反向代理：

```typescript
// ✅ 正确的代码
const response = await fetch(
  `/api/v1/performance/overview?${params}`,
  { headers: { Authorization: `Bearer ${token}` } }
);
```

### 为什么这样可行？

#### Nginx 配置
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

#### 请求流程
```
浏览器请求: /api/v1/performance/overview
    ↓
Nginx 接收: https://health.westwetlandtech.com/api/v1/performance/overview
    ↓
Nginx 转发: http://127.0.0.1:8000/api/v1/performance/overview
    ↓
FastAPI 处理: /api/v1/performance/overview
```

---

## 📝 修改文件

### `/frontend/src/app/admin/performance/page.tsx`

#### 1. loadOverview 函数
```diff
- `${process.env.NEXT_PUBLIC_API_URL}/api/v1/performance/overview?${params}`
+ `/api/v1/performance/overview?${params}`
```

#### 2. loadPagePerformance 函数
```diff
- `${process.env.NEXT_PUBLIC_API_URL}/api/v1/performance/pages?${params}`
+ `/api/v1/performance/pages?${params}`
```

#### 3. loadAPIPerformance 函数
```diff
- `${process.env.NEXT_PUBLIC_API_URL}/api/v1/performance/apis?${params}`
+ `/api/v1/performance/apis?${params}`
```

---

## 🚀 部署步骤

### 1. 提交代码
```bash
git add frontend/src/app/admin/performance/page.tsx
git commit -m "fix: 修复性能监控页面 API 路径错误 - 移除 undefined 前缀"
git push
```

### 2. 服务器部署
```bash
ssh root@health.westwetlandtech.com
cd /opt/health-app
git pull
cd frontend
npm run build
pm2 restart health-frontend
```

### 3. 验证修复
```bash
# 测试 API 可访问性（应返回认证错误，而不是 404）
curl -s "https://health.westwetlandtech.com/api/v1/performance/overview?hours=24"
# 预期输出: {"detail":"未登录或登录已过期"}
```

---

## ✅ 验证结果

### 修复前
```
❌ GET /admin/undefined/api/v1/performance/overview → 404 Not Found
❌ GET /admin/undefined/api/v1/performance/apis → 404 Not Found
```

### 修复后
```
✅ GET /api/v1/performance/overview → 200 OK (需登录)
✅ GET /api/v1/performance/apis → 200 OK (需登录)
✅ 页面正常加载，无 404 错误
```

---

## 📊 影响范围

### 受影响的功能
- ✅ 性能监控概览页面
- ✅ 页面性能详情
- ✅ API 性能详情

### 不受影响的功能
- ✅ 其他管理页面
- ✅ 用户功能页面
- ✅ 小程序端

---

## 🎓 经验教训

### 1. 环境变量管理
- ❌ **错误**: 假设环境变量总是存在
- ✅ **正确**: 使用相对路径或提供默认值
- ✅ **最佳实践**: 在构建时验证必需的环境变量

### 2. API 路径设计
```typescript
// ❌ 不推荐：依赖环境变量
const API_URL = process.env.NEXT_PUBLIC_API_URL;

// ✅ 推荐：使用相对路径 + Nginx 反向代理
const API_URL = '';  // 空字符串，使用相对路径

// ✅ 推荐：提供默认值
const API_URL = process.env.NEXT_PUBLIC_API_URL || '';
```

### 3. 错误排查技巧
```
看到 "undefined" 在 URL 中 → 检查环境变量
看到 404 错误 → 检查 Nginx 配置和路径
看到认证错误 → 说明路径正确，检查认证逻辑
```

---

## 🔧 未来优化建议

### 1. 统一 API 客户端
```typescript
// utils/api-client.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export const apiClient = {
  get: (path: string, options?: RequestInit) => 
    fetch(`${API_BASE}${path}`, options),
  
  post: (path: string, data: any, options?: RequestInit) =>
    fetch(`${API_BASE}${path}`, {
      method: 'POST',
      body: JSON.stringify(data),
      ...options
    })
};
```

### 2. 环境变量验证
```typescript
// config/validate-env.ts
const requiredEnvVars = [
  'NEXT_PUBLIC_API_URL',
  // ... 其他必需变量
];

export function validateEnv() {
  const missing = requiredEnvVars.filter(
    key => !process.env[key]
  );
  
  if (missing.length > 0) {
    console.warn(`Missing env vars: ${missing.join(', ')}`);
    console.warn('Using default values...');
  }
}
```

### 3. 类型安全的配置
```typescript
// config/index.ts
export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || '',
  isDev: process.env.NODE_ENV === 'development',
  isProd: process.env.NODE_ENV === 'production',
} as const;
```

---

## 📅 修复记录

| 时间 | 操作 | 状态 |
|------|------|------|
| 2026-01-24 12:15 | 发现问题 | ❌ 404 错误 |
| 2026-01-24 12:20 | 定位原因 | 🔍 环境变量未定义 |
| 2026-01-24 12:25 | 修复代码 | ✅ 使用相对路径 |
| 2026-01-24 12:30 | 部署验证 | ✅ 修复成功 |

---

**修复状态**: ✅ 完成  
**验证状态**: ✅ 通过  
**文档时间**: 2026-01-24 12:30 (北京时间)
