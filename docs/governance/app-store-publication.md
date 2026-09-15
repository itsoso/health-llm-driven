# App Store 公共上架闭环

仅在正式 App Store 送审、审核后发布或公开可见性核验时读取本参考。TestFlight-only、
OTA 和本地扫码包不需要加载它。

## 完成定义

把下列事实分开记录：

1. 精确版本和 build 已上传并被本轮 App Review 接受；
2. 价格、税务分类、有效合同和目标销售地区已经配置；
3. 版本发布方式已经执行或可自动执行；
4. 目标地区在 App Store Connect 中为 `Available`；
5. 目标地区的公开商店查询返回相同 App ID、名称和版本。

前四项中的内部状态不能替代第五项。只有目标地区全部满足 4–5，才能报告“全部目标地区公开上架”；
若仅核验约定的验收 storefront，应逐项报告通过地区，抽样地区通过不能代表全部地区。
真机下载、安装和核心路径 smoke 仍是独立证据，不由网页可见性替代。

Apple 状态和地区语义以官方的
[App and submission statuses](https://developer.apple.com/help/app-store-connect/reference/app-information/app-and-submission-statuses)
为准；页面动作以
[Manage availability for your app](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/manage-availability-for-your-app-on-the-app-store)
和
[Select an App Store version release option](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/select-an-app-store-version-release-option)
为准。

## 送审前一次收集

先复用当前会话中仍适用的用户授权及已知候选信息；仅补齐缺失或变化的项目：

- App ID、bundle ID、version、build 和目标提交记录；
- 销售范围：全部地区或明确的地区集合；
- 发布方式：审核后自动发布、手动发布、指定时间或分阶段更新；
- 公开验收 storefront 从已授权目标地区中选择；面向中国用户且销售范围包含中国时包含 `cn`，全球发布再包含 `us`；
- 需要用户接管的账号、合同或付款事项。

用户说“全部搞定 / 直接上架 / 一气完成”时，沿用已授权的发布方式和地区；尚未配置且无法从
当前任务确定的发布方式或范围，先准备具体可审核方案再询问。仅在用户明确要求全球发布时
选择全部可用国家或地区，实际集合以本次 ASC 回读为准；不要从“上架”二字推断全球销售范围。

## 送审前闸门

在提交 App Review 前完成只读核对：

1. 精确 build 与受审 SHA、bundle ID、version、签名和 production profile 一致；
2. CI、后端兼容性、同包验收、审核账号、隐私问卷和审核说明已通过各自 Gate；
3. Business 中所需合同有效，价格计划和税务分类完整；
4. `Pricing and Availability -> App Availability` 已配置目标地区；
5. 版本页的 release option 与用户选择一致。

如果 `App Availability` 未配置，先把界面准备到：

```text
Set Up Availability -> All Countries or Regions / Specific Countries or Regions
-> Next -> Confirm
```

`Confirm` 会改变未来公开销售范围。最终确认前核对候选、目标范围及已有授权。
提交 App Review、手动发布和更改地区各自有授权边界；已授权的相同范围不重复索取确认，
候选或范围改变、用户撤销授权，或当前执行环境明确要求新的批准时，再按实际变化处理。

## 审核后按状态继续

- `Rejected` / `Metadata Rejected` / `Unresolved Issues`：读取原始审核信息，回到修复和同包验证，
  不发布、不猜原因。
- `Pending Developer Release`：说明审核已通过但仍需发布。把 `Release This Version` 的确认页
  准备好；已有该候选公开发布授权则继续，否则在最终确认前请求授权；随后回读状态。
- `Processing for Distribution`：Apple 正在处理，继续有界监控，不重提、不重造包。
- `Ready for Distribution`：版本可分发，但仍核对有效合同和每个目标地区的 App Store 状态；
  如果页面提示 removed from sale 或仍显示 `Set Up Availability`，先修复地区配置。
- `Available on App Release`：地区等待手动或计划发布，不等于用户已经可以下载。
- `Processing to Available`：地区正在同步，不等于完成。Apple 的手动发布说明提示公开显示可能需要
  最多 24 小时；将其作为排查节点，不保证每一种地区处理状态都在该时限内结束。
- `Available`：该地区的 ASC 状态已就绪，再做公开商店回读。

审核通过不等于公开上架。一次缺少地区配置的恢复路径可如下记录；仅记录实际观察到的状态，
不得补写未发生的步骤：

```text
Ready for Distribution
-> Processing to Available
-> Available
-> public lookup resultCount=1
```

## 公开商店回读

对每个验收 storefront 使用 Apple 的 ID lookup；ID 查询比名称搜索稳定：

```bash
curl -fsS --max-time 20 \
  "https://itunes.apple.com/lookup?id=<APP_ID>&country=<STOREFRONT>" \
  | jq '{resultCount, results: [.results[] | {
      trackId, trackName, version, trackViewUrl, currentVersionReleaseDate
    }]}'
```

Apple 的 [iTunes Search API lookup](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/LookupExamples.html)
支持按 iTunes/App ID 查询。验收时要求：

- `resultCount=1`；
- `trackId` 等于目标 App ID；
- `trackName` 和 `version` 等于本轮预期；
- `trackViewUrl` 可打开对应地区的公开 App Store 产品页。

`resultCount=0`、产品页“无法找到”或旧版本仍可见，都只能报告为尚未完成或仍在传播。
公开结果与 ASC 冲突时，以“未完成”处理并保留两侧证据。

## Apple 异步处理与静默监控

当 ASC 显示 `Processing for Distribution` 或 `Processing to Available`：

- 复用同一 App ID、版本、地区和已知任务，不重复提交、发布或修改 availability；
- 仅在用户要求后续监控或已授权定期检查时，通过产品提供的 heartbeat/automation 按约定间隔
  做只读检查；未指定间隔可使用 30 分钟，状态不变时保持安静；没有该授权则报告当前状态；
- 仅在公开成功、失败、状态回退、需要用户操作或超过 24 小时时通知；
- 成功后停用该监控，防止重复通知；
- 超过 24 小时仍在 processing 时，保留开始时间和地区状态，向用户报告并准备支持请求；
  未经授权不得联系 Apple。

监控不能通过刷新频率制造“更快发布”，也不能把自动化叙述当成公开页面证据。

## 完成报告

最终只报告可验证事实：

- version、build、App ID；
- 发布方式和配置地区数；
- ASC 目标地区状态；
- 已通过的公开 storefront、查询时间和产品页链接；
- 真机安装/核心路径是否另行验证；
- 未完成项、Apple 处理时限，以及已安排的下一次自动检查（如有）。

若任一目标地区尚未满足公开回读，不能使用“全部上线完成”。只有发布动作确已完成且 ASC
仍显示处理状态时，才使用“发布动作已完成，Apple 仍在处理”；其他情况报告实际未完成项。
