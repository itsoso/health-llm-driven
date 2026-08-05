# PRD: iOS 1.3.3 App Store 正式发布

> Status: approved for implementation
> Owner: product / mobile release
> Approved: 2026-08-05
> Related spec: `docs/specs/active/2026-08-05-ios-1-3-3-app-store-release.md`

## 1. Goal

在 2026-08-07（周五）前完成小巴 iOS 1.3.3 的新正式构建、同包真机验收和 App Store 提交；若 Apple 在本周内批准，则在生产健康检查通过后手动公开发布。

“本周发布”不等于承诺 Apple 的审核完成时间。团队可承诺的是：无已知红项地完成正式包并提交审核，随后及时响应审核问题。

## 2. Problem

现有 Build 240 虽由 Xcode 26.2 / iOS 26.2 SDK 构建，但来源于 2026-07-29，未嵌入当前主干最近的登录、Garmin、Agent 和饮食改动。现有送审材料仍指向 1.3.2 Build 237，并保留 Draft、审核账号和联系电话等占位状态。

代码审查还发现，记录页的鼻炎卡向所有用户展示两种具体处方药及固定剂量，并在点击时自动创建药物和服药记录。该行为既不是对用户既有医嘱的忠实记录，也可能被审核员理解为应用在提供处方或剂量决定。

## 3. Requirements

- R1：正式版本号为 1.3.3，使用新的 Store Build（构建号不低于 241）。
- R2：1.3.3 进入功能冻结；新需求进入 1.3.4。
- R3：删除鼻炎卡中的具体处方药、默认剂量和自动建药路径；失败必须让用户感知。
- R4：审核账号可使用账号密码直接登录，不依赖短信、邀请码、HealthKit、Garmin 或特殊硬件。
- R5：App Privacy、年龄分级、医疗器械状态、审核联系人、审核说明和截图与精确 Build 一致。
- R6：生产包只启用标准 iPhone 能力；实验性 Rokid、Watch、Siri、后台定位和诊断入口保持关闭。
- R7：所有可选权限均由用户主动触发；拒绝权限后仍可使用文字对话和手工记录。
- R8：同一个 Store Build 完成真机、医疗边界、隐私、账号删除、分享、Garmin/HealthKit 和恢复性验收。
- R9：审核期间冻结 production OTA 渠道和审核账号状态。
- R10：审核批准后采用手动发布，并完成生产真机和服务健康验证。

## 4. Non-Goals

- 不新增健康功能、跨端能力、支付、订阅或新数据源。
- 不在 1.3.3 集中清理全部 lint 警告或做大规模重构。
- 不把免责声明当作保留处方或剂量决策行为的理由。
- 不直接提交 Build 240，也不依赖首次启动 OTA 才获得本次发布代码。
- 不在 Apple 批准前承诺公开上架日期。

## 5. Success Criteria

1. 全量相关测试、类型检查、依赖安全和发布闸门通过。
2. 独立安全评审对用药记录改动给出 GO。
3. 精确 IPA 显示版本 1.3.3、构建号不低于 241，并由 Xcode 26 / iOS 26 SDK 或更新版本构建。
4. 最终送审闸门在审核机上通过，且不依赖提交到 git 的账号密码或私密真机证据。
5. App Store Connect 接收构建并进入审核。
6. Apple 批准后，生产服务健康且用户可下载、登录并完成核心文字路径。

## 6. Release Boundaries

- 健康、用药和账号数据的事实源仍是后端；客户端不得推导处方或剂量。
- App Store Connect 是隐私标签、年龄分级、审核详情和提交状态的最终事实源。
- EAS 构建 ID、git commit、IPA 工具链字段和真机证据共同定义精确发布包。
- production OTA 在提交审核到公开上线完成期间保持冻结。

## 7. Authoritative External Requirements

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Upcoming submission requirements](https://developer.apple.com/news/upcoming-requirements/)
- [App privacy responses](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/)
- [Account deletion](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
- [Regulated medical device declaration](https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status)
