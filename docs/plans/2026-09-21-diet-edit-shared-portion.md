# 饮食修正与聚餐份额交付计划

依据 [spec](../specs/active/2026-09-21-diet-edit-shared-portion.md) 与 [PRD](../prd/2026-09-21-diet-edit-shared-portion.md)。

- T1 Backend：先写失败测试；结构化份额加入现有重算契约及幂等摘要；稳定整桌基准与自然话语法；owner/CAS/酒精边界不变。
- T2 Mobile：先写失败测试；共享份额解析/选择器，聊天内联与饮食编辑接同一契约；明确重算反馈与失败状态。
- T3 验证：相关 pytest/Jest、TypeScript、PostgreSQL CAS、schema 类型同步、系统地图与 CI-mode 集成；独立安全审查。
- T4 发布：仅在 G3/G4 通过且干净目标 revision CI 绿时，先后端再 production OTA；核对在线 revision/服务健康/OTA manifest；用户实际路径待确认。

无新依赖、DB migration 或原生权限；保持用户与其他 agent 改动。范围仅饮食修正，不重开此前已发布项目。
