# 补剂快速勾选弹窗

| Field | Value |
| --- | --- |
| status | building |
| current_stage | S5 implementation |
| Controller | product-pipeline |
| Overlay | safety-gate |

## 用户需求

“是否可以做一个快速补剂弹出UI 让我check选中”。

## G1 准入

裁决: PASS。本人既有补剂已服事实的人工确认 UI；按用户持续授权推进实现及部署/OTA，无额外读写授权扩张。

## Discovery / G2

裁决: GO。现有 /supplements/me/date/{date} 和 /records/batch 可复用，整批归属验证和事务已存在。独立 reviewer cold_recovery_safety 指出跨设备首次并发可碰唯一约束、取消为最后写入覆盖；不承诺严格跨设备幂等。客户端只传 ID/taken/date，不能将常规剂量当实际剂量。

定义及实施规划合并见 docs/specs/2026-10-16-supplement-quick-checkin.md。

## 实施与验证

新增独立弹窗和受限服务；聊天加号作为入口。先合成 RED/GREEN 与账户/时间/未知结果边界，随后独立 G4、精确 CI、部署和 OTA。当前尚未交付。

运行 ledger: `docs/_generated/harness-runs/0f47337d455b.jsonl`（本地，不提交）。聊天菜单测试先 RED（缺补剂入口），实现后 83 项 GREEN。System Map 校验通过，现有开放 PR 无本功能对应项；远端 main 已核对为本会话上次发布的 4d0913b45。

## S5 / G4 验证

实现完成，独立 G4 GO（cold_recovery_safety，冻结文件摘要见 /tmp/reva-supplement-picker-g4.json）。聊天及专项共 107 项通过；既有后端契约 65 项通过（SQLite 快速契约，非 PostgreSQL 证明）；TypeScript、System Map 和 diff 检查通过。实际 RN Web 组件合成预览验证 320/390 宽度、勾选数量及已服禁选；未读取真实健康记录，未做真实模型评测。原生模拟器交互尚未验证，不冒充设备验收。

管理入口已改为“查看补剂记录”，不声称记录页能新增清单。只记录显式勾选的已服事实，不写实际剂量。跨设备并发不承诺严格 exactly-once。

待执行：候选精确 SHA 完整 CI、CI-mode 集成闸、发布回执核对、后端部署及 trusted OTA validate/publish。
