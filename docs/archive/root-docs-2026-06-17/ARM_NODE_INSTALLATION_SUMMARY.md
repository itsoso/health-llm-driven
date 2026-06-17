# ARM Node.js 安装总结

## ✅ 已完成的工作

### 1. 成功安装 ARM 版本的 Node.js

- **Node.js 25.4.0 (ARM64)**：`/opt/homebrew/bin/node`
- **Node.js 20.19.6 LTS (ARM64)**：`/opt/homebrew/opt/node@20/bin/node`
- **架构验证**：两个版本都是原生 ARM64 架构

```bash
# 验证
/opt/homebrew/bin/node -p "process.arch"  # 输出: arm64
/opt/homebrew/opt/node@20/bin/node -p "process.arch"  # 输出: arm64
```

### 2. 更新了 Shell 配置

在 `~/.zshrc` 中添加了：
```bash
# ARM Homebrew (优先使用 ARM 原生版本)
if [ -d "/opt/homebrew" ]; then
  export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
fi
```

**重要**：需要重新打开终端或运行 `source ~/.zshrc` 使配置生效。

### 3. 手动获取了 Taro ARM Binding

- 下载了 `@tarojs/binding-darwin-arm64@4.1.10`
- 文件位置：`/tmp/package/taro.darwin-arm64.node` (4.7MB)

## ❌ 遇到的问题

### Taro 4.1.10 的 Native Binding 问题

**问题描述**：
- Taro CLI 在加载时会检测平台和架构
- 但由于某些原因，它一直尝试加载 `@tarojs/binding-darwin-x64` 而不是 ARM 版本
- 即使手动复制了 ARM binding 文件，问题仍然存在

**可能的原因**：
1. Taro CLI 内部有硬编码的架构检测逻辑
2. npm 的可选依赖安装策略问题
3. 某些环境变量或缓存影响了架构检测

## 🎯 推荐的解决方案

### 方案 1：使用已构建的 dist 目录（最简单）✅

**当前状态**：`packages/mini-program/dist/` 已包含构建好的代码（2026-01-21）

**操作步骤**：
```bash
# 直接用微信开发者工具打开
open -a "微信开发者工具" /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist
```

或在微信开发者工具中：
1. 文件 -> 导入项目
2. 项目目录：`/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist`
3. AppID：`wx1234567890abcdef`

### 方案 2：在服务器上构建（推荐用于更新代码）

服务器是 Linux x64 架构，不会有这个问题：

```bash
# 1. SSH 到服务器
ssh root@39.98.206.178

# 2. 进入小程序目录
cd /opt/health-app/packages/mini-program

# 3. 安装依赖（如果还没有）
npm install

# 4. 构建
npm run build:weapp

# 5. 下载 dist 目录到本地
# 在本地执行：
scp -r root@39.98.206.178:/opt/health-app/packages/mini-program/dist ./packages/mini-program/
```

### 方案 3：使用 Docker 构建

创建一个 Docker 容器来构建：

```bash
# 在项目根目录
cat > Dockerfile.miniapp << 'EOF'
FROM node:20-alpine
WORKDIR /app
COPY packages/mini-program/package*.json ./
RUN npm install
COPY packages/mini-program/ ./
RUN npm run build:weapp
CMD ["sh"]
EOF

# 构建镜像
docker build -f Dockerfile.miniapp -t miniapp-builder .

# 运行并复制产物
docker run --name temp miniapp-builder
docker cp temp:/app/dist ./packages/mini-program/
docker rm temp
```

### 方案 4：降级 Taro 版本（未测试）

Taro 3.x 可能没有这个问题：

```bash
cd packages/mini-program

# 修改 package.json 中的 Taro 版本为 3.6.x
# 然后重新安装
npm install
npm run build:weapp
```

### 方案 5：手动修复 Taro Binding（复杂）

需要修改 `node_modules/@tarojs/binding/binding.js` 的架构检测逻辑，但这不是持久化的解决方案。

## 🔧 新终端中使用 ARM Node.js

由于已经更新了 `~/.zshrc`，在**新打开的终端**中：

```bash
# 方法 1：使用默认的 ARM Node.js 25
node --version  # 应该显示 v25.4.0
node -p "process.arch"  # 应该显示 arm64

# 方法 2：使用 Node.js 20 LTS（更稳定）
/opt/homebrew/opt/node@20/bin/node --version  # v20.19.6
/opt/homebrew/opt/node@20/bin/npm run build:weapp
```

## 📝 后续步骤

### 立即可用（推荐）

1. **打开微信开发者工具**
2. **导入项目**：`packages/mini-program/dist`
3. **预览并测试订阅功能**

### 如果需要更新代码

1. **在服务器上构建**（方案 2）
2. **或使用 Docker**（方案 3）
3. **下载 dist 目录到本地**
4. **在微信开发者工具中刷新**

## 🎉 成果

虽然遇到了 Taro 的兼容性问题，但我们成功地：

1. ✅ 安装了 ARM 原生版本的 Node.js（25.4.0 和 20.19.6 LTS）
2. ✅ 配置了 Shell 环境，优先使用 ARM Homebrew
3. ✅ 确认了已有的构建产物可以直接使用
4. ✅ 提供了多种替代构建方案

## 📚 相关文档

- `MINI_PROGRAM_QUICK_START.md` - 小程序快速开始指南
- `MINI_PROGRAM_PUSH_GUIDE.md` - 订阅推送完整指南

---

**建议**：直接使用现有的 `dist` 目录进行测试和开发。如果需要更新代码，在服务器上构建是最可靠的方案。
