# 小程序编译指南

## 问题描述

在 ARM Mac 上编译小程序时遇到错误：

```
[ app.json 文件内容错误] dist/app.json: In the directory dist/ specified by "miniprogramRoot" in project.config.json, app.json is not found in that directory.
```

**根本原因**：
- `dist/` 目录为空或只有 `project.config.json`
- 小程序代码未编译
- ARM Mac 上 Taro 4.x 存在 native binding 兼容性问题

## ✅ 解决方案：在服务器上编译

由于 ARM Mac 上 Taro 4.x 的 native binding 问题，最可靠的方案是在 Linux 服务器上编译。

### 完整步骤

```bash
# 1. 在服务器上拉取最新代码并编译
ssh root@39.98.206.178 "cd /opt/health-app && git pull && cd packages/mini-program && npm run build:weapp"

# 2. 删除本地旧的 dist 目录并下载新的
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
rm -rf dist
scp -r root@39.98.206.178:/opt/health-app/packages/mini-program/dist .

# 3. 验证文件
ls -la dist/
# 应该看到：app.js, app.json, app.wxss, pages/, assets/ 等
```

### 一键脚本

创建 `packages/mini-program/build-on-server.sh`：

```bash
#!/bin/bash
set -e

echo "📦 在服务器上编译小程序..."
ssh root@39.98.206.178 "cd /opt/health-app && git pull && cd packages/mini-program && npm run build:weapp"

echo "📥 下载编译结果到本地..."
cd "$(dirname "$0")"
rm -rf dist
scp -r root@39.98.206.178:/opt/health-app/packages/mini-program/dist .

echo "✅ 编译完成！"
echo "📱 现在可以在微信开发者工具中打开项目："
echo "   项目目录: $(pwd)/dist"
```

使用方法：

```bash
cd packages/mini-program
chmod +x build-on-server.sh
./build-on-server.sh
```

## 📱 在微信开发者工具中使用

### 方法 1：直接打开 dist 目录

```bash
open -a "微信开发者工具" /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist
```

### 方法 2：在工具中导入

1. 打开微信开发者工具
2. 文件 -> 导入项目
3. 项目目录：`/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program/dist`
4. AppID：`wx169f93db056a7dd5`

## 🔧 本地编译（不推荐）

如果确实需要在本地编译，可以尝试以下方法：

### 方法 1：使用 Docker

```bash
# 创建 Dockerfile
cat > Dockerfile.miniapp << 'EOF'
FROM node:20-alpine
WORKDIR /app
COPY packages/mini-program/package*.json ./
RUN npm install
COPY packages/mini-program/ ./
RUN npm run build:weapp
CMD ["sh"]
EOF

# 构建并运行
docker build -f Dockerfile.miniapp -t miniapp-builder .
docker run --name temp miniapp-builder
docker cp temp:/app/dist ./packages/mini-program/
docker rm temp
```

### 方法 2：使用 Rosetta 2（未测试）

```bash
# 使用 x86_64 架构运行 Node.js
arch -x86_64 npm run build:weapp
```

## 📋 编译后的文件结构

```
dist/
├── app.js                 # 主程序逻辑
├── app.json              # 小程序配置
├── app.wxss              # 全局样式
├── assets/               # 静态资源
│   └── icons/
├── pages/                # 页面目录
│   ├── index/
│   ├── diet/
│   ├── diet-recommendation/  # 饮食推荐页面
│   ├── workout/
│   └── ...
├── base.wxml             # 基础模板
├── common.js             # 公共代码
├── taro.js               # Taro 运行时
├── vendors.js            # 第三方库
└── project.config.json   # 项目配置
```

## ⚠️ 常见问题

### Q1: 为什么不能在 ARM Mac 上直接编译？

**A**: Taro 4.x 的 native binding 在 ARM Mac 上有兼容性问题：

```
Error: Cannot find module '@tarojs/binding-darwin-x64/taro.darwin-x64.node'
```

即使安装了 `@tarojs/binding-darwin-arm64`，Taro CLI 仍然会尝试加载 x64 版本。

### Q2: 服务器上的 Taro 版本是多少？

**A**: 服务器使用 Taro 3.6.38（更稳定），而本地 `package.json` 中是 4.1.10。

### Q3: 编译后需要提交 dist 目录吗？

**A**: 不需要。`dist/` 目录在 `.gitignore` 中，只在本地使用。

### Q4: 如何更新小程序代码？

```bash
# 1. 修改源代码（src/）
# 2. 提交并推送到 GitHub
git add .
git commit -m "feat: 更新小程序功能"
git push

# 3. 重新编译
./build-on-server.sh

# 4. 在微信开发者工具中刷新
```

## 📚 相关文档

- `ARM_NODE_INSTALLATION_SUMMARY.md` - ARM Node.js 安装总结
- `MINI_PROGRAM_QUICK_START.md` - 小程序快速开始指南
- `MINI_PROGRAM_DIET_RECOMMENDATION_FIX.md` - 饮食推荐页面修复

## 🎯 本次修复总结

### 问题
- 小程序开发者工具报错：找不到 `app.json`
- `dist/` 目录为空或不完整

### 解决方案
1. ✅ 在服务器上编译小程序（避免 ARM 兼容性问题）
2. ✅ 使用 `scp` 下载编译结果到本地
3. ✅ 验证所有页面（包括 `diet-recommendation`）已正确编译

### 验证
```bash
# 检查关键文件
ls -la dist/app.json          # ✅ 存在
ls -la dist/pages/diet-recommendation/  # ✅ 存在
```

---

**建议**：将 `build-on-server.sh` 脚本添加到项目中，方便后续使用。
