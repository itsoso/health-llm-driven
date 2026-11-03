# 聊天记录成功卡片必须来自真实结果

| 字段 | 值 |
| --- | --- |
| 状态 | 修复已合入 main；后端与 iOS OTA 已发布并独立回读；模拟器与设备接收验收未验证 |
| Workflow | quick_fix → mobile-ota |
| Overlay | safety-gate |

## 问题与证据

用户截图中，餐厅体验请求的回复仍要求确认记录类型，但后面出现绿色“已记录”。
按截图关键词做有界、只读生产查询，回合没有工具调用、没有服务端卡片、没有写入回执，
且服务端把它标为普通聊天完成。相邻后续回合被阻止，不能将顶部全局红条归因于该条体验请求。
仓库仅保存结论和合成用例，不保存用户原文、店名、身份或健康载荷。

客户端 `RecordCardSpec` 根据“记录”等关键词或 `health_record` 工具名称匹配，
其 `build` 无条件生成“已记录”。本地补卡也对待确认、部分完成状态开放。
本次只修复错误成功展示；不扩大生活事件或饮食写入授权，不将餐厅评价推断成食物摄入。

## 修复

- 停止从本地关键词或工具名称构造记录成功卡片；保留服务端记录卡渲染。
- 本地查询补卡只适用于已完成回合，待确认及部分完成仅展示服务端明确下发的结果。
- 保留已经保存的餐食回执与卡片，不因后续分析失败撤销事实。

## 验证

- 新增合成体验请求、仅有工具名、失败记录请求和非完成终态用例。
- RED：5 项失败，1 项已通过，确认原实现可复现错误。
- GREEN：卡片 registry、聊天引擎、历史恢复和回合状态 4 套测试，324 项通过。
- TypeScript `--noEmit`、秘密扫描、`git diff --check` 和 System Map 检查通过。
- 本地 CI-mode 发布不变量集成闸：5,849 passed、68 skipped、127 subtests passed，退出码 0。
- 独立安全审查 G4：GO；复核人独立重跑上述 324 项关联回归。
- 精确候选 `8a1933a1b071d273230cabf5d7f16d7c4fc9cf47`：[CI 41581413412](https://github.com/itsoso/health-llm-driven/actions/runs/41581413412) 全部 32 个 job 成功。
- [发布预检 41582838460](https://github.com/itsoso/health-llm-driven/actions/runs/41582838460) 成功，仅执行 preflight，其余发布 job 按目标跳过；预检不代表部署。
- 未修改数据库、后端接口、模型提示词、原生依赖或权限。
- 模拟器视觉验收与设备接收 OTA 尚未验证。

## 发布证据

- 授权与运行版本分别核验：旧安装授权为 `035848ef505425c71ca7d0952b6b456c2dc3c677`，其后端工作区未启动；交接前实际生产为有成功回执的 `e87f04d51dbd328b408c7fa787297d0b32e4e3b4`。
- 经独立审查，保留原锁、完整发布历史和回执，完成 canonical 源码 staging、同仓库只读凭据刷新、旧未启动身份关闭及普通 canonical 授权轮换。未把其他版本的成功回执冒充旧授权的工作区成功；未创建备份或恢复旧配置。
- 本候选授权已安装；[后端部署 41584978128](https://github.com/itsoso/health-llm-driven/actions/runs/41584978128) 成功。
- 独立回读：生产 HEAD 为上述候选且工作树干净，后端 `SUCCEEDED` 回执摘要为 `b7ccd3df24fbc42eeb4c077e696cdfbc40109be14a246518e3ee8c5e2c94060b`，runtime terminal 为同候选 `COMMITTED`，业务租约已释放。后端、worker、beat 均 active，API、数据库、Redis、Celery 健康。
- 生产至候选的 Mobile 原生配置、依赖锁、iOS/Android 与插件路径无差异；trusted OTA 的原生 cohort 和 runtime 闸通过。
- [OTA validate 41585571469](https://github.com/itsoso/health-llm-driven/actions/runs/41585571469) 成功，包含原生来源、依赖、iOS 制品与发布前验证；validate 阶段未消费发布 claim。
- [OTA publish 41585823665](https://github.com/itsoso/health-llm-driven/actions/runs/41585823665) 成功，目标为 iOS / production / runtime `1.3.6`。
- 更新组 `5a673058-c663-4bc9-9f62-18eed3eb490c`，更新 ID `01a19ff8-b635-7c0b-a463-c5ec2b3020b4`；服务端同候选 `SUCCEEDED` 回执摘要 `6ddd405cefe19ad779a34098111c87bb18a3621bc11217f6c312ef93e52d5042`，其 intent 与 verified 回执摘要均独立回读一致，原业务租约已释放。
- 从公开 Expo manifest 独立核验更新 ID、project、runtime、启动 bundle 摘要及全部资源摘要集合，与服务端原 claim 的制品证明一致。后端同候选、干净工作树、运行终态与健康状态保持正确；公开健康接口再次返回 healthy。
- 发布成功不等于用户设备已加载更新。没有操作真机，也未将模拟器截图、旧包或本地测试作为设备接收证明。
