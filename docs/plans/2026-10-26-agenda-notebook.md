# 记事本实施规划

1. LifeData 增加有界 notebook 数组（id/title/body）；仍持久化到原 JSON 文档，不改表结构。旧客户端缺字段且已有笔记时拒绝保存，显式空数组允许清空。
2. Web 增加独立 NotebookPanel；编辑通过原 workspace edit/save 链路，保持 owner key、epoch、write lock、CAS 和撤销。移动端 DTO/导入校验同步。
3. 测试 UI 创建/保存/重开/搜索/删除/撤销/冲突/账号切换；后端边界、存储、隔离及旧客户端数据保护；PostgreSQL 验证现有事务语义。生成双端 API 类型，检查 System Map。
4. 独立 G4 审查后接续统一发布；当前其他操作者交接未完成，不能启动并行部署。Web/后端发布与 Mobile OTA 分别核验。
