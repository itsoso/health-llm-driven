# 小程序白屏问题调试指南

## 问题现象
清除缓存后，小程序全面白屏

## 已完成的修复

### 1. 简化渲染逻辑
- 移除复杂的 IIFE（立即执行函数表达式）
- 使用标准的条件渲染
- 移除不必要的调试日志

### 2. 增强错误处理
- 添加全局错误监听 (`Taro.onError`)
- 添加未处理的 Promise 拒绝监听 (`Taro.onUnhandledRejection`)
- 在关键位置添加 try-catch 保护

## 调试步骤

### 1. 在微信开发者工具中调试

1. **打开调试器控制台**
   - 点击微信开发者工具右上角的"调试器"
   - 切换到"Console"标签

2. **查看错误信息**
   - 检查是否有红色错误信息
   - 查找以下关键字：
     - `全局错误:`
     - `未处理的Promise拒绝:`
     - `App渲染错误:`
     - `初始化失败:`
     - `页面显示时错误:`
     - `请求失败:`

3. **检查网络请求**
   - 切换到"Network"标签
   - 查看是否有请求失败（红色）
   - 特别关注：
     - `/api/wechat/login` - 登录接口
     - `/api/garmin/today` - Garmin数据接口
     - `/api/daily-recommendation/today` - AI建议接口

4. **检查存储**
   - 切换到"Storage"标签
   - 查看 `access_token` 是否存在
   - 查看 `user_name` 是否存在

### 2. 常见问题排查

#### 问题1: 域名未配置
**错误信息**: `域名未配置，请在微信公众平台添加合法域名`

**解决方案**:
1. 登录微信公众平台 (mp.weixin.qq.com)
2. 进入"开发" -> "开发管理" -> "开发设置"
3. 在"服务器域名"中添加:
   - request合法域名: `https://health.westlandtech.com`
   - uploadFile合法域名: `https://health.westlandtech.com`
   - downloadFile合法域名: `https://health.westlandtech.com`

#### 问题2: Token过期
**错误信息**: `登录已过期，请重新登录`

**解决方案**:
1. 在微信开发者工具中，点击"清除缓存" -> "清除数据缓存"
2. 重新编译小程序
3. 重新登录

#### 问题3: API请求失败
**错误信息**: `连接失败: fail` 或 `网络请求失败`

**解决方案**:
1. 检查后端服务是否正常运行
2. 检查 nginx 配置是否正确
3. 检查防火墙设置
4. 在服务器上查看后端日志:
   ```bash
   journalctl -u health-backend.service -f
   ```

#### 问题4: 页面渲染错误
**错误信息**: 控制台有 JavaScript 错误

**解决方案**:
1. 记录完整的错误堆栈
2. 检查是否是某个组件导致的
3. 尝试注释掉部分代码，逐步定位问题

### 3. 临时调试模式

如果需要更详细的日志，可以临时启用调试模式：

1. 打开 `packages/mini-program/src/pages/index/index.tsx`
2. 在 `loadHomeData` 函数开头添加:
   ```typescript
   console.log('=== 开始加载首页数据 ===');
   ```
3. 在关键位置添加 console.log
4. 重新编译并查看控制台输出

### 4. 检查编译产物

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program

# 检查 dist 目录是否完整
ls -la dist/

# 检查 app.json 是否正确
cat dist/app.json

# 检查首页是否编译成功
ls -la dist/pages/index/
```

### 5. 完全重新构建

如果以上方法都无效，尝试完全重新构建：

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program

# 清理所有构建产物和依赖
rm -rf dist node_modules

# 重新安装依赖
npm install

# 重新构建
npm run build:weapp
```

## 联系支持

如果问题仍然存在，请提供以下信息：

1. 微信开发者工具控制台的完整错误信息（截图）
2. Network 标签中失败的请求详情（截图）
3. Storage 标签中的存储内容（截图）
4. 后端服务日志（如果有相关错误）

## 最近的代码变更

- 2026-01-13: 简化 IIFE 表达式，移除调试日志
- 2026-01-13: 添加全局错误监听和 try-catch 保护
