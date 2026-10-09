# 每日分析固定使用阿里云 Token Plan

状态：本地实现、回归验证、独立安全复审完成；未提交、未部署。

## 用户目标与范围

`/daily-insights` 的一天与七天分析、个性化建议固定使用阿里云 Token Plan，不使用全局活跃模型或旧 API。保留现有认证后端接口，以服务端持有凭据，继续执行 AI consent、目的地校验、PII 脱敏、用量与配额检查，以及原健康分析提示及规则安全告警。外部建议页签不在本次范围。

## 实现

- 新增 TokenPlanHealthAnalyzer，复用现有健康分析提示与配置 TOKENPLAN_API_KEY、TOKENPLAN_BASE_URL、TOKENPLAN_MODEL；不修改其他服务的通用全局模型。
- 专用工厂显式创建 tokenplan provider，保留追踪与脱敏；禁用跨模型自动恢复。配置错误或服务失败明确标记不可用，不调用旧 provider。
- 每日建议移除 legacy RAG 调用及导入，因为其检索会调用旧 embeddings API；其他服务的 RAG 保持原行为。
- Redis、数据库现有 JSON 缓存按路由版本、provider、模型及 use_llm 模式检查，拒绝旧结果和失败 AI 结果；不需要 schema 迁移。
- 修复七天摘要的 health_summary/key_insights/today_focus 字段，并展示各项 AI 建议。
- 前端显示 Token Plan 来源和失败状态；刷新消费本次响应，避免额外生成请求。请求绑定固定 subjectId，账号变更时丢弃返回结果，查询缓存按用户隔离。
- 解析失败不返回原始模型健康内容，不当作成功分析。

## 新鲜验证

后端使用隔离 Python 3.12 环境、项目 requirements 与 requirements-dev，测试数据为合成数据；独立本机 PostgreSQL 17 测试库，未读取生产凭据或健康记录。

```text
pytest tests/test_daily_insights_tokenplan.py tests/test_llm_refactor.py
       tests/test_llm_factory.py tests/test_air_quality_unknown_city_honesty.py
       tests/test_llm_usage_tracker.py tests/test_llm_policy_recovery.py
       tests/test_legacy_rag_pipeline_gate.py tests/test_ai_consent_subject_binding.py
       tests/test_pii_scrub.py -q --no-cov --tb=short
92 passed
vitest run src/app/daily-insights/page.test.tsx
            src/app/daily-insights/components/AiInsightsSection.test.tsx
4 passed
npx tsc --noEmit
exit 0
```

新增行为先运行失败测试，再实现。回归覆盖固定 provider、禁止恢复、PII 处理、旧 Redis/DB 缓存重建、用户隔离、七天字段、legacy RAG 不调用、错误可见、刷新期间换账号不污染缓存。

独立只读 safety-gate reviewer 首轮 NO-GO：legacy embeddings 出口、pending refresh 缓存主体变化。修复并补回归后，最终 GO（仅代码安全审查，不是发布准入）。

## 发布边界与待办

- 当前共享 main 工作区包含其他任务的改动，不能作为干净发布 revision。
- canonical System Map 已按当前代码重新生成；central check 的 canonical 与 doc drift 通过，mobile-nav 因其他移动端导航改动而失败，尚未豁免。
- 尚未进行项目 CI-mode 集成闸、精确目标 revision 的真实 CI、部署或线上 Token Plan 验收。
- 生产 TOKENPLAN 配置及成功调用未在本任务中验证，不把 mock/合成回归宣称为线上成功。
