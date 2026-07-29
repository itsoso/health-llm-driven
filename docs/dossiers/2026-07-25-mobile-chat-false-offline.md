| 字段 | 值 |
|---|---|
| feature | mobile-chat-false-offline |
| status | shipping |
| current_stage | S7 / G6 pending |
| date | 2026-07-25 |

# Dossier: Mobile 图片对话假离线

## 用户原话

> 分析问题原因 并修复

## 现象与根因

用户从相机、相册或其他 App 返回后发送带图消息，设备状态栏已有 Wi-Fi/蜂窝网络，但客户端提示“网络不可用”，服务端没有收到请求，输入框继续保留图片草稿。

根因是 `useChatEngine` 把 `NetInfo.fetch()` 的瞬时状态作为发送硬闸。iOS 前后台和系统选择器切换期间，NetInfo 可能短暂返回旧的 `isConnected=false` 或 `isInternetReachable=false`；客户端因此在真实 API 请求前直接失败。

## 设计裁决

- NetInfo 只作为建议性 UI 信号，不作为 Agent 发送成功与否的真源。
- 每次发送都尝试真实 API；以服务端持久化回执作为清理输入框和图片草稿的唯一依据。
- 真实网络失败继续走现有 XHR 错误、草稿保留、相同 turn 幂等重试链路。
- 不修改图片编码、上传载荷、Agent API 或后端数据。

## Gate Ledger

| Gate | 状态 | 依据 |
|---|---|---|
| G1 准入 | PASS | 修复既有 Mobile Agent 对话可靠性，不增加产品对象或自治能力 |
| G2 可行性+安全 | PASS | 删除不可靠前置闸门；服务端持久化回执仍是提交真源 |
| G3 测试 | PASS | `useChatEngine` 59 项、输入框联合回归 115 项、图片草稿 8 项；TypeScript 通过，目标 lint 0 error |
| G4 安全/隐私 | PASS | 图片仍只在发送时从私有草稿目录读取；失败不清理草稿，不扩大网络或数据权限 |
| G5 部署健康 | PASS | production OTA 已发布，update group、iOS update 与提交锚点均回读一致 |
| G6 上线验证 | PENDING | 等待真机相机/相册返回后立即发送图片验证 |

## G1 准入

**裁决**: PASS

这是既有 Mobile Agent 对话输入和提交链路的可靠性修复，映射既有对话 Turn 与饮食记录核心循环；不新增产品对象、健康建议、数据出口或自治写入。

## G5 部署健康

**裁决**: PASS

- production OTA runtime `1.3.2`；
- update group `e1222cbc-c8d0-43b1-b448-e1245a0bbbac`；
- iOS update `019f98f9-1bbe-758b-9e68-089c3b42fb62`；
- 提交锚点 `5185ff7103d4844ea51438b92c12b1a87143fe1a`；
- OTA 脚本已回读校验 update group、iOS update 和提交锚点。

## TestFlight Build 237

- 从干净 `main` 提交 `f6e4308c` 执行 EAS production 构建和自动提交；
- App Version `1.3.2`，Build `237`，EAS Build ID `7a7df837-50b8-46ed-97a8-983fc8ea3a07`；
- EAS Submission ID `e8202581-365c-4c6a-83c5-16b6b92928b0`；
- EAS 已完成 App Store distribution 构建，Apple 已确认二进制上传成功；
- App Store Connect Build ID `caeb6880-2fae-41a9-8324-58156b8e4ac3`；
- App Store Connect API 回读 `processingState=VALID`、`expired=false`、`internalBuildState=IN_BETA_TESTING`，Build 237 已可供内部 TestFlight 安装；
- 外部状态为 `READY_FOR_BETA_SUBMISSION`，本轮未提交外部 Beta Review。

## 当前检查点

S7 / G6 pending：根因、修复、本地回归与 production OTA 已完成，等待真机从相机/相册返回后立即发送图片验证。
