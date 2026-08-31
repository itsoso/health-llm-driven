# PRD: 益家知研受审 System KB 上线

## 目标

用户明确指定“益家知研 / 皮皮妈妈”时，小巴必须在该来源的已审定内容中真实检索，
展示来源回执，并在无匹配内容时诚实零命中；不得用通用 System KB 冒充。

## 用户问题

当前路由已能识别指定来源，但该来源被标为 `not_released`。旧 Markdown 原文不是可
直接上线的医学依据：缺少逐条出处，且包含儿童退烧和补剂剂量等高风险内容。

## 需求

1. reviewed System KB 文档可声明 `metadata.source_collections`。
2. System KB 搜索支持可选的精确 source collection，所有检索通道只在该集合内融合。
3. “益家知研 / 皮皮妈妈”别名只映射到 `yijia_reviewed`；不得映射整个 System KB。
4. 第一批内容只覆盖锚点场景：
   - 没有充分证据支持用膳食补充剂预防或治疗 COVID-19；
   - 高风险用户应尽早评估规范治疗，治疗窗口和相互作用由医生/药师核对；
   - 不生成补剂、退烧药或抗病毒药个体剂量。
5. 命名来源无命中时返回该来源零命中，不做通用回退。

## 验收

- 指定益家知研查询“新冠发烧补剂”至少命中一条该集合的 reviewed claim。
- 响应包含 requested source、resolved source、released 状态和受审证据来源。
- 同一查询指定任意不存在的来源仍为 `unresolved`。
- 益家知研查询不会返回只属于其他集合的高分文档。
- 通用 `knowledge_search` 行为保持兼容。

## 不做

- 不发布 `supplement_knowledge.md` 或 `pipi_mama/*.md` 全文。
- 不把公众号身份当作医学权威。
- 不给补剂、退烧药、抗病毒药的自动剂量或处方建议。
- 不新增数据库表，不改客户端。
