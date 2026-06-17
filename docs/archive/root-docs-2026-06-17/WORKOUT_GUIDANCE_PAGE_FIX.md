# 运动指导页面加载问题修复

## 问题现象

访问 https://health.westwetlandtech.com/workout-guidance 时页面显示 "加载中..." 无法正常加载。

## 问题原因

根据服务器日志分析，发现 Next.js Server Action 缓存不匹配错误：

```
Error: Failed to find Server Action "d8dfbc64". 
This request might be from an older or newer deployment.
```

### 根本原因

1. **部署缓存问题**：前端代码更新后，Next.js 的 `.next` 构建缓存与新代码不匹配
2. **Server Action ID 变化**：Next.js 在构建时为 Server Actions 生成唯一 ID，代码更新后 ID 改变
3. **浏览器缓存**：用户浏览器缓存了旧版本的 JavaScript 代码，尝试调用已不存在的 Server Action

## 解决方案

### 1. 清理构建缓存并重新构建

```bash
ssh root@39.98.206.178 "cd /opt/health-app/frontend && rm -rf .next && npm run build"
```

这会：
- 删除旧的 `.next` 构建目录
- 重新构建整个前端应用
- 生成新的 Server Action ID

### 2. 重启前端服务

```bash
ssh root@39.98.206.178 "systemctl restart health-frontend"
```

### 3. 验证服务状态

```bash
# 检查服务状态
systemctl status health-frontend

# 测试页面响应
curl -I http://localhost:30001/workout-guidance
```

## 执行结果

✅ **已成功修复**

```
● health-frontend.service - Health App Frontend
     Active: active (running) since Wed 2026-01-21 13:13:42 CST
     
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 12355
```

## 预防措施

### 1. 改进部署流程

在 `deploy.sh` 中添加清理缓存步骤：

```bash
# 部署前端时
echo "清理构建缓存..."
rm -rf .next

echo "重新构建..."
npm run build

echo "重启服务..."
systemctl restart health-frontend
```

### 2. 添加版本控制

在前端添加版本号，方便追踪部署：

```typescript
// frontend/src/utils/version.ts
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || '1.0.0';
```

### 3. 浏览器缓存策略

在 `next.config.js` 中配置合理的缓存策略：

```javascript
module.exports = {
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, must-revalidate',
          },
        ],
      },
    ];
  },
};
```

### 4. 健康检查

添加健康检查端点，监控服务状态：

```typescript
// frontend/src/app/api/health/route.ts
export async function GET() {
  return Response.json({
    status: 'ok',
    version: process.env.NEXT_PUBLIC_APP_VERSION,
    timestamp: new Date().toISOString()
  });
}
```

## 常见 Next.js 部署问题

### 1. Server Action 不匹配

**症状**：`Failed to find Server Action`

**原因**：构建缓存与代码不匹配

**解决**：清理 `.next` 目录重新构建

### 2. 静态资源 404

**症状**：CSS/JS 文件加载失败

**原因**：Nginx 配置或构建输出路径问题

**解决**：检查 Nginx 配置和 `next.config.js` 的 `basePath`

### 3. 环境变量未生效

**症状**：API 调用失败，使用了错误的 URL

**原因**：`.env.local` 未正确加载

**解决**：确保环境变量文件存在且格式正确

### 4. 内存不足

**症状**：构建过程中服务器卡死

**原因**：Next.js 构建需要大量内存

**解决**：增加 swap 空间或升级服务器配置

## 监控建议

### 1. 日志监控

```bash
# 实时查看前端日志
journalctl -u health-frontend -f

# 查看最近的错误
journalctl -u health-frontend --since "1 hour ago" | grep -i error
```

### 2. 性能监控

```bash
# 检查服务资源占用
systemctl status health-frontend

# 查看进程详情
ps aux | grep next
```

### 3. 访问监控

```bash
# 检查 Nginx 访问日志
tail -f /var/log/nginx/access.log | grep workout-guidance

# 检查错误日志
tail -f /var/log/nginx/error.log
```

## 相关文档

- [Next.js Deployment](https://nextjs.org/docs/deployment)
- [Next.js Caching](https://nextjs.org/docs/app/building-your-application/caching)
- [Server Actions](https://nextjs.org/docs/app/building-your-application/data-fetching/server-actions-and-mutations)

## 总结

此次问题是由于 Next.js 部署时构建缓存不匹配导致的。通过清理 `.next` 目录并重新构建，问题已完全解决。

**当前状态**：✅ 页面正常访问

**访问地址**：https://health.westwetlandtech.com/workout-guidance

**验证方法**：
1. 访问页面，应该能看到完整的运动指导表单
2. 勾选 Debug 模式复选框
3. 点击"获取运动前指导"按钮
4. 应该能看到紫色的 Debug 面板展示 AI 决策过程
