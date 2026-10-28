# 小气候守护图标

2026-10-28：用户确认 C 方向并要求将开口朝下版本替换当前系统图标。

- 设计源：`app-icon-guardian-v1.png`，1024×1024、不透明 RGB PNG。
- 视觉：深绿背景、米白色下开口保护弧、杏色小生命与两枚深绿眼睛。
- Slogan 保留「关照自己的状态」，不写入桌面图标。
- Mobile 主图与 adaptive 图字节相同；启动图 512px、favicon 48px。Web 路由图 512px、public favicon 64px；Watch 按现有 asset catalog 尺寸派生。
- Mac 应用图标生成器读取同一 Mobile 主图，应用系统所需圆角；状态栏功能图标不变。
- 大头像、登录页与小尺寸聊天头像复用 Mobile 主图，避免独立云朵绘制遗留。

## 生成来源

使用内置 imagegen，以对话中确认的下开口设计板为编辑输入；生成后仅以 sharp 做确定性缩放和 RGB 格式规范化。旧候选设计保留为历史，不是本次备份。

生成提示词：

> Production asset extraction from the approved reference. Output ONE square app icon only, no comparison board. Reproduce faithfully the LARGE LEFT icon's artwork: deep evergreen green background, thick warm ivory circular protective arch OPEN AT BOTTOM (6 o'clock), its lower rounded endpoints symmetric, small upright apricot pebble companion with two dark green vertical oval eyes centered inside. Preserve exactly this design, silhouette, spacing, colors and gentle satin shading. Remove everything outside that large icon. IMPORTANT production requirements: square canvas filled EDGE TO EDGE with the same dark evergreen background all the way into all four square corners. NO rounded outer tile corners, NO ivory exterior margin, NO outer shadow, NO border or frame. The operating system will round the square corners. Central symbol with about 12 percent padding from all canvas edges; match reference character and ring proportions. No words, no slogan, no brand text, no miniature variants. Opaque RGB-style final square icon. Do not redesign or add details.

## 交付边界

本次更改原生图标及启动资源，需要新原生包，不能通过 OTA 宣称已安装的桌面图标更新。原有 282/source838 送审候选及其截图不代表这次图标版本。新的生产发布须在现有发布收尾、精确候选 CI 和原生验收后执行。

## 本地验证

- 回归先失败：compact 头像仍使用旧云朵矢量、启动页仍为旧背景色；修复后 4 套件共 25 项通过（app-icon-assets、XiaoBaAvatar、ChatHeader、EmptyStateHome）。
- Mobile TypeScript 与 design:check 通过；System Map 完整检查通过（显式将仓库 `.venv/bin` 加入 PATH，使用现有 Python 3.12）。
- 17 个跨端 PNG 均为方形、不透明，且与设计源按目标尺寸确定性派生结果相同；Expo prebuild 生成的 iOS AppIcon 与设计源像素完全一致。
- Mac ICNS 已通过既有 Swift 生成器重新生成；未修改状态栏功能图标。
- 设计源 SHA256：`1996cbba876eebc2f4a379149552f79a8bc08df800596f7c2a3a47e97461b011`。
- 资产纳入本次本地提交与审查；尚未推送、部署或替换商店送审包，工作树原有 benchmark 与发布文档改动保留。
- 本地 iOS Release 原生构建成功（`/tmp/xiaoqihou-guardian-build.log`），包名 `life.executor.health`、显示名「小气候」；已安装至 iPhone 17 / iOS 26.5 模拟器并成功启动。此为当前工作树的本地构建，不是已上传的282包。
- 模拟器实际视觉验收通过：登录页展示下开口守护图标；返回桌面后「小气候」的新 launcher 图标可见。截图 `tmp/xiaoqihou-guardian/home-screen.png`。没有登录账户、发送验证码或读写健康数据。
