# 2026-06-29 Mobile 阿衡人格文案收敛计划

> 目标:在本周可发布版本中,让 Mobile 主路径和通用 App Store/MVP surface 的用户可见人格统一为 `阿衡`。

## 背景

- App 名和发布材料已经锁定为 `阿衡`。
- 首页 Daily Artifact、试用入口、onboarding、体检导入动态卡片和部分权限/分享文案仍可能让用户看到 `Reva`、`复元` 或泛称 `健康助理`。
- 技术符号、组件名、路由名和设计系统 token 暂不重命名,避免扩大构建风险。

## 范围

本批处理:

- 首页 Daily Artifact 的 ask action 无障碍标签。
- 首页“试试阿衡”入口卡标题、副标题、无障碍标签。
- `/reva-onboarding` 示例模式进入按钮与说明文案。
- `/reva` hub 中用户可见 tab、空态、输入框和计划说明。
- Chat 体检导入结果动态卡片的主按钮。
- Chat 附件权限、体检导入权限、语音分享、家庭邀请、运动分享、隐私政策、分享落地页等通用用户可见文案。

本批不处理:

- `Reva*` 组件名、类型名、文件名、route 名。
- 设计系统注释中的 Reva token/history。
- Rokid 专页和 Rokid SDK 相关文案;它们有独立外设语义和较大测试面,后续单独做。

## 验收

- `DailyArtifactCard` 测试覆盖 `询问阿衡今日行动`。
- `RevaTryEntryCard` 测试覆盖 `试试阿衡`、标题 `阿衡`、副标题 `阿衡对话`。
- `reva-onboarding` 测试覆盖 `进入阿衡`。
- `MedicalExamImportResultCard` 测试覆盖 `让阿衡解读这次导入`。
- 目标旧称扫描不再命中:
  - `询问 Reva`
  - `试试新版复元`
  - `进入复元`
  - `问问复元`
  - `问复元`
  - `复元会`
  - `复元把`
  - `复元对话`
  - `健康助理`
  - `5 分钟看见 Reva`
  - `Reva 只给`
  - `让 Reva`
  - `允许 Reva`
  - `Reva 提供`

## 状态

- 当前状态:已实现并通过本地测试。
