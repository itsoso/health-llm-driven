# Plan: 益家知研受审 System KB 上线

## 数据流

```text
explicit named source
  -> deterministic source binding
  -> canonical collection yijia_reviewed
  -> reviewed-only System KB hybrid search scoped to the collection
  -> source receipt + matched transformed claims
  -> LLM synthesis under no-dose/no-substitution boundary
```

## 实现任务

1. 在 System KB search API 增加可选 `source_collection`；加载 reviewed 文档后先按
   `metadata.source_collections` 精确收窄，PostgreSQL FTS 结果也按同一 doc-id 集合过滤；
   无指定来源时排除 `named_collection_only`，保持通用库原排序。
2. 将益家知研别名从 `not_released` 切换为 canonical `yijia_reviewed/released`，仅该
   canonical 值触发 source-scoped search；`reviewed_system_kb` 继续通用搜索。
3. 添加两条经权威资料校准的转化 claim 和一个 eval case，更新 artifact manifest。
4. 增加服务层、Agent executor、artifact 及零回退测试，先 RED 再 GREEN。
5. 运行 System KB release gate、相关回归、LLM gate、独立安全评审和 CI。
6. 从干净 main 部署；生产只读回放验证指定源命中且没有通用来源混入。

## 安全承重墙

- `generic_serving_document_filters()` 仍是所有结果的前置条件。
- source collection 只能进一步收紧，不能放宽 reviewed/hold/archive policy。
- 原始旧文只作 discovery 输入，不写入运行时 artifact body。
- claims 必须带官方来源、有效期、claim boundary 和 no-dose safety tags。
- source-scoped 零命中不调用第二次通用搜索。

## 回滚

代码和 artifact 同 commit 回滚；部署会重新导入上一版本 artifact。无 schema/data
migration，别名恢复 `not_released` 即可 fail-closed。
