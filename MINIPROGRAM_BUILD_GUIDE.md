# 小程序编译指南

**更新时间**: 2026-01-22

## 问题说明

在 ARM64 Mac (Apple Silicon) 上使用命令行编译小程序时，可能遇到 Taro binding 模块错误：

```
Error: Cannot find module '@tarojs/binding-darwin-x64/taro.darwin-x64.node'
```

**原因**: Taro 的 native binding 模块在某些环境下可能无法正确识别 ARM64 架构。

## 推荐方案：使用微信开发者工具

### 步骤 1: 打开微信开发者工具

1. 启动微信开发者工具
2. 选择"导入项目"或"打开项目"

### 步骤 2: 导入小程序项目

**项目路径**:
```
/Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
```

**项目配置**:
- AppID: 使用你的小程序 AppID（在 `project.config.json` 中）
- 项目名称: health-llm-driven 小程序

### 步骤 3: 编译项目

1. 微信开发者工具会自动识别 Taro 项目
2. 点击工具栏的"编译"按钮
3. 等待编译完成

### 步骤 4: 预览和调试

1. **模拟器预览**: 在开发者工具中直接预览
2. **真机预览**: 点击"预览"按钮，扫码在手机上查看
3. **调试**: 使用开发者工具的调试面板

### 步骤 5: 上传代码

1. 确认功能正常后，点击"上传"按钮
2. 填写版本号和备注
3. 提交审核（如需要）

## 代码更新流程

### 1. 修改代码

在你的编辑器（如 Cursor）中修改代码：
```
packages/mini-program/src/pages/index/index.tsx
```

### 2. 保存文件

保存后，微信开发者工具会自动检测文件变化。

### 3. 重新编译

- **自动编译**: 如果开启了"自动编译"，保存后自动编译
- **手动编译**: 点击"编译"按钮

### 4. 查看效果

在模拟器或真机上查看更新后的效果。

## 本次修复内容

### 修复的问题

**文件**: `packages/mini-program/src/pages/index/index.tsx`

**错误**: `TypeError: Cannot read property 'body_battery' of undefined`

**修复内容**:
```typescript
// 修复前
{homeData.garmin?.body_battery_current ?? '--'}

// 修复后
{homeData?.garmin?.body_battery_current ?? '--'}
```

**修复位置**:
- 第 717 行: `body_battery_most_charged`
- 第 794 行: `body_battery_current`
- 第 558 行: `calories_total` 条件判断
- 第 702 行: `total_sleep_duration`

### 验证步骤

1. 打开微信开发者工具
2. 导入项目：`packages/mini-program`
3. 点击"编译"
4. 在模拟器中打开首页
5. 确认以下内容正常显示：
   - 身体电量卡片（🔋）
   - 电量峰值数据
   - 能量平衡计算
   - 睡眠时长

## 替代方案：命令行编译（高级）

如果确实需要使用命令行编译，可以尝试以下方法：

### 方案 A: 使用 Rosetta 2

```bash
# 使用 x86_64 架构运行 Node.js
arch -x86_64 zsh
cd /Users/liqiuhua/work/personal/health-llm-driven/packages/mini-program
npm run build:weapp
```

### 方案 B: 强制使用 ARM64 绑定

```bash
# 1. 清除缓存
cd /Users/liqiuhua/work/personal/health-llm-driven
rm -rf node_modules/.pnpm/@tarojs+binding*

# 2. 设置环境变量
export npm_config_arch=arm64
export npm_config_platform=darwin

# 3. 重新安装
pnpm install

# 4. 编译
cd packages/mini-program
npm run build:weapp
```

### 方案 C: 修改 package.json

在 `packages/mini-program/package.json` 中添加：

```json
{
  "optionalDependencies": {
    "@tarojs/binding-darwin-arm64": "^4.1.10"
  }
}
```

然后重新安装依赖。

## 常见问题

### Q1: 微信开发者工具找不到项目配置

**A**: 确保导入的是 `packages/mini-program` 目录，而不是项目根目录。

### Q2: 编译后页面空白

**A**: 
1. 检查控制台是否有错误
2. 确认 API 地址配置正确（`src/services/request.ts`）
3. 检查是否已登录

### Q3: 真机预览时无法访问 API

**A**: 
1. 在微信公众平台配置合法域名：
   - `https://health.westwetlandtech.com`
2. 开发阶段可以在开发者工具中勾选"不校验合法域名"

### Q4: 代码修改后没有生效

**A**:
1. 确认文件已保存
2. 点击"编译"按钮重新编译
3. 清除缓存：工具 → 清除缓存 → 清除所有缓存

## 项目结构

```
packages/mini-program/
├── src/
│   ├── pages/          # 页面
│   │   ├── index/      # 首页
│   │   ├── diet/       # 饮食记录
│   │   ├── workout/    # 运动记录
│   │   └── ...
│   ├── services/       # API 服务
│   ├── types/          # 类型定义
│   └── assets/         # 静态资源
├── config/             # Taro 配置
├── project.config.json # 微信小程序配置
└── package.json        # 依赖配置
```

## 相关文档

- [Taro 官方文档](https://taro-docs.jd.com/)
- [微信小程序开发文档](https://developers.weixin.qq.com/miniprogram/dev/framework/)
- [项目快速开始指南](./MINI_PROGRAM_QUICK_START.md)

## 总结

**推荐方式**: 使用微信开发者工具进行开发和编译

**优点**:
- ✅ 无需处理 native binding 问题
- ✅ 自动编译，实时预览
- ✅ 完整的调试工具
- ✅ 真机预览和上传功能

**命令行编译**: 仅在 CI/CD 或特殊场景下使用

---

**文档维护**: AI Assistant  
**最后更新**: 2026-01-22
