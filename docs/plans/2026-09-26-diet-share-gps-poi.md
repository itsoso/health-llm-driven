# 高德分享地点实现计划

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

父流程与 Gate：[Dossier](../dossiers/2026-09-26-diet-share-gps-poi.md)。

1. 先为认证代理、GPS 转换、结果投影/脱敏/限流写 RED 测试，再实现 backend API/schema/service/config，无 DB 写入。
2. 先写 Mobile service 和地点编辑器 RED：同意、定位、搜索、候选预填、人工修改、取消/失效。实现独立组件，Composer 只交换确认 label，复用旧截图代次门禁。
3. 接入编辑器，修复全宽布局；更新隐私文案，双端契约同批验证。
4. 相关 pytest/Jest/tsc/lint/秘密/地图闸；独立安全审查固定 diff。G3/G4 失败回实现；未配置 Key 不伪造真实联调。
5. 发布是后续独立授权/Gate；需后端 Key 与正式隐私披露准备。无迁移；失败回退手填，旧功能持续可用。
