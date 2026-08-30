---
name: extend-safety-or-specialist
description: "在 backend 加一条 Safety Guardian 规则 或 一个 Orchestrator Specialist。当要新增安全规则/专科 agent 时使用。含 @register、engine 注册、防循环导入、doc-drift 登记、测试接线等易漏步骤。"
---

# 扩展 Safety 规则 / Specialist

两个扩展点共享同一个坑:**doc-drift 登记 + 测试接线容易漏**。改完都要跑 `doc-drift-fix` + 测试。
安全规则属敏感面 → 上线前走 `safety-gate`。

## 加一条 Safety Rule

1. 在 `backend/app/agents/safety_guardian/rules/<file>.py` 写函数,加 `@register` 装饰器(自动注册,不用改 engine)。
   - 签名:`(twin: HealthTwin) -> Optional[Alert] | List[Alert]`。
   - 只读 Twin,不开 db(规则是纯 twin→alerts 函数;要的数据先在 builder 填进 Twin 分区)。
2. **新文件**才需在 `engine.py` 的 `_load_rule_modules()` 里 import 该模块(已有文件加函数不用)。
3. **doc-drift 登记**(必做,否则 CI 红):
   - `scripts/check_doc_drift.py` 的 `EXPECTED["safety_rules"]` 加该文件 @register 数(**纯数据文件无 @register 也要登记为 0**,防 `unknown rule file`)。
   - 运行 generator 更新 `docs/_generated/system-map.json`；叙事文档只链接生成真源，禁止手写总数。
4. 测试到 `tests/test_safety_guardian.py`:正例(命中→Alert,severity/requires_medical_attention 对)+ 反例(不命中→静默)。
5. 跑 `doc-drift-fix` + `pytest tests/test_safety_guardian.py`。**上线走 `safety-gate`**。

## 加一个 Specialist

1. 建 `backend/app/agents/<name>/` 目录,实现 Specialist Protocol:`applies_to(intent, twin) -> bool` + `run(twin, context) -> SpecialistFinding`。
2. 在 `backend/app/orchestrator/specialists.py` 的 `_build_registry()` 注册(按依赖顺序)。
3. **防循环导入**:`<name>/__init__.py` **不要** import specialist 类(由 `specialists.py` 直接 import)。
4. **doc-drift 登记**:让扫描器识别新 Specialist，运行 generator 更新
   `docs/_generated/system-map.json`；叙事文档不手写 Specialist 总数。
5. 测试到 `tests/test_specialists.py`(applies_to 正反 + run 产出 shape)。
6. 跑 `doc-drift-fix` + `pytest tests/test_specialists.py tests/test_orchestrator.py`。

## 共同验证

```bash
cd backend && source venv/bin/activate
export SECRET_KEY=test-secret-key-32-chars-minimum!! GARMIN_ENCRYPTION_KEY=mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=
pytest tests/test_safety_guardian.py tests/test_specialists.py tests/test_orchestrator.py -q --no-cov
../scripts/system-map-check.sh          # exit 0
```

> 规则需要的新数据要先进 Twin:加 Twin 分区字段 → 在 `builder.py` 填；必须验证 Phase A 传入 session 与 Phase B 并行 session 的一致性边界。结构变化统一走 `doc-drift-fix`，不在叙事里手写分区计数。
