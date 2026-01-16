# iOS App 构建指南

本项目支持将 Web 前端打包成原生 iOS App。

## 前置要求

1. **macOS 系统** - 只有 Mac 才能构建 iOS App
2. **Xcode** - 从 App Store 安装最新版
3. **Apple Developer 账号** - 发布到 App Store 需要 ($99/年)
4. **CocoaPods** - iOS 依赖管理工具

```bash
# 安装 CocoaPods（如果没有）
sudo gem install cocoapods
```

## 构建步骤

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 构建 iOS 版本

```bash
# 构建静态文件并同步到 iOS 项目
npm run build:ios
```

### 3. 安装 iOS 原生依赖

```bash
cd ios/App
pod install
cd ../..
```

### 4. 打开 Xcode

```bash
npm run open:ios
```

或直接打开 `frontend/ios/App/App.xcworkspace`

### 5. 在 Xcode 中配置

1. 选择 **App** target
2. 在 **Signing & Capabilities** 中：
   - 选择你的 Team（Apple Developer 账号）
   - 设置 Bundle Identifier: `life.executor.health`
3. 选择目标设备或模拟器
4. 点击 **▶️ Run** 运行

## 发布到 App Store

### 1. 配置 App 信息

在 Xcode 中设置：
- Display Name: `自律靠AI`
- Bundle Identifier: `life.executor.health`
- Version: `1.0.0`
- Build: `1`

### 2. 创建 Archive

1. 选择 **Any iOS Device** 作为目标
2. 菜单: **Product** → **Archive**
3. 等待构建完成

### 3. 上传到 App Store Connect

1. 在 Archive 窗口点击 **Distribute App**
2. 选择 **App Store Connect**
3. 按提示上传

### 4. 在 App Store Connect 提交审核

1. 登录 https://appstoreconnect.apple.com
2. 创建新 App
3. 填写 App 信息、截图、描述
4. 提交审核

## 常用命令

```bash
# 构建 iOS 版本
npm run build:ios

# 打开 Xcode
npm run open:ios

# 同步 Web 资源到 iOS（不重新构建）
npm run sync:ios

# 仅构建静态文件（不同步）
npm run build:native
```

## 调试

### 在模拟器中调试

1. 在 Xcode 中选择模拟器
2. 点击 Run
3. 可以使用 Safari 的 Web Inspector 调试

### 在真机上调试

1. 用 USB 连接 iPhone
2. 在 iPhone 上信任开发者证书
3. 在 Xcode 中选择你的设备
4. 点击 Run

## 项目结构

```
frontend/
├── ios/                    # iOS 原生项目
│   └── App/
│       ├── App/            # Xcode 项目
│       │   └── public/     # Web 资源（构建时复制）
│       ├── App.xcworkspace # Xcode 工作空间
│       └── Podfile         # CocoaPods 配置
├── out/                    # Next.js 静态导出目录
├── capacitor.config.ts     # Capacitor 配置
└── package.json
```

## 注意事项

1. **API 地址**: iOS App 直接调用 `https://health.westwetlandtech.com/api`
2. **HTTPS**: iOS 要求所有网络请求使用 HTTPS
3. **隐私权限**: 如需使用相机、相册等，需在 `Info.plist` 中配置权限描述
4. **推送通知**: 需要额外配置 APNs 证书

## 更新 App

修改 Web 代码后：

```bash
# 重新构建并同步
npm run build:ios

# 在 Xcode 中重新运行
```
