# Debug 模式故障排查

## 问题现象

打开 Debug 模式后，页面没有展示 Debug 信息面板。

## 已执行的修复步骤

### 1. ✅ 重新构建前端
```bash
cd /opt/health-app/frontend
rm -rf .next
npm run build
systemctl restart health-frontend
```

### 2. ✅ 重启后端服务
```bash
systemctl restart health-backend
```

**状态：** 所有服务已重启并正常运行

## 当前服务状态

### 后端服务
```
● health-backend.service - Health App Backend
     Active: active (running) since Wed 2026-01-21 13:15:56 CST
     Uvicorn running on http://127.0.0.1:8000
```

### 前端服务
```
● health-frontend.service - Health App Frontend
     Active: active (running) since Wed 2026-01-21 13:13:42 CST
     Next.js 14.2.35 running on http://0.0.0.0:30001
```

## 验证步骤

### 1. 清除浏览器缓存

**重要：** 由于前端代码已更新，需要强制刷新浏览器缓存。

**方法：**
- **Chrome/Edge**: `Ctrl + Shift + R` (Windows) 或 `Cmd + Shift + R` (Mac)
- **Firefox**: `Ctrl + F5` (Windows) 或 `Cmd + Shift + R` (Mac)
- **Safari**: `Cmd + Option + R`

或者：
1. 打开开发者工具 (F12)
2. 右键点击刷新按钮
3. 选择 "清空缓存并硬性重新加载"

### 2. 检查网络请求

打开浏览器开发者工具 (F12)，切换到 Network 标签：

1. 勾选 Debug 模式复选框
2. 点击 "获取运动前指导"
3. 查找 `pre-workout-guidance` 请求
4. 检查请求 URL 是否包含 `?debug=true`
5. 查看响应数据是否包含 `debug` 字段

**预期结果：**
```
Request URL: .../pre-workout-guidance?goal_id=6&debug=true
Response: {
  "success": true,
  "workout_type": "...",
  "debug": {
    "steps": [...],
    "data_sources": {...},
    "reasoning": [...]
  },
  ...
}
```

### 3. 检查控制台错误

在开发者工具的 Console 标签中，查看是否有 JavaScript 错误。

常见错误：
- `Cannot read property 'steps' of undefined` - debug 对象不存在
- `Unexpected token` - JSON 解析错误
- `Network error` - API 调用失败

## 测试 API

### 使用 curl 测试（需要有效 token）

```bash
# 测试不带 debug
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" | jq 'has("debug")'
# 应该返回: false

# 测试带 debug=true
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" | jq 'has("debug")'
# 应该返回: true

# 查看 debug 结构
curl -X POST "https://health.westwetlandtech.com/api/v1/workout/pre-workout-guidance?debug=true" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" | jq '.debug.steps'
# 应该返回步骤数组
```

## 可能的问题和解决方案

### 问题 1: 浏览器缓存了旧代码

**症状：** Debug 开关存在，但点击后没有反应

**解决：** 强制刷新浏览器（见上文）

### 问题 2: API 未返回 debug 字段

**症状：** Network 请求中响应没有 debug 字段

**解决：**
```bash
# 重启后端
ssh root@39.98.206.178 "systemctl restart health-backend"

# 检查日志
ssh root@39.98.206.178 "journalctl -u health-backend -f"
```

### 问题 3: 前端代码未更新

**症状：** Debug 开关不存在

**解决：**
```bash
# 重新部署前端
cd /opt/health-app/frontend
git pull
npm install
rm -rf .next
npm run build
systemctl restart health-frontend
```

### 问题 4: React 状态未更新

**症状：** 勾选 Debug 开关但 API 请求没有 debug 参数

**检查：** 在浏览器控制台运行：
```javascript
// 查看 debugMode 状态
console.log(document.querySelector('#debugMode').checked);
```

## 调试技巧

### 1. 添加控制台日志

在浏览器控制台中，可以临时添加日志：

```javascript
// 监听 API 响应
const originalFetch = window.fetch;
window.fetch = function(...args) {
  return originalFetch.apply(this, args).then(response => {
    response.clone().json().then(data => {
      console.log('API Response:', data);
      console.log('Has debug?', 'debug' in data);
    });
    return response;
  });
};
```

### 2. 检查 React 组件状态

使用 React DevTools 扩展：
1. 打开 React DevTools
2. 找到 `WorkoutGuidancePage` 组件
3. 查看 `debugMode` 和 `preGuidance` 状态

### 3. 查看服务器日志

实时查看后端日志：
```bash
ssh root@39.98.206.178 "journalctl -u health-backend -f | grep -E 'debug|workout-guidance'"
```

## 预期行为

### Debug 模式关闭时
- ✅ 页面正常显示运动指导
- ✅ 没有紫色的 Debug 面板
- ✅ API 请求不包含 `debug=true`
- ✅ 响应不包含 `debug` 字段

### Debug 模式开启时
- ✅ 页面顶部显示紫色的 "🔍 AI 决策过程" 面板
- ✅ 显示 7 个决策步骤
- ✅ 显示 15-20 条推理过程
- ✅ 可以展开查看详细数据来源
- ✅ API 请求包含 `?debug=true`
- ✅ 响应包含完整的 `debug` 对象

## 联系支持

如果以上步骤都无法解决问题，请提供以下信息：

1. 浏览器类型和版本
2. Network 标签中的完整请求和响应
3. Console 标签中的错误信息
4. 是否已清除浏览器缓存
5. 服务器日志截图

## 快速检查清单

- [ ] 已强制刷新浏览器（Ctrl+Shift+R）
- [ ] 后端服务正常运行
- [ ] 前端服务正常运行
- [ ] Debug 开关可以勾选
- [ ] Network 请求包含 `debug=true`
- [ ] API 响应包含 `debug` 字段
- [ ] 页面显示紫色 Debug 面板

## 最后更新

2026-01-21 13:16 - 后端和前端服务已重启，所有代码已部署
