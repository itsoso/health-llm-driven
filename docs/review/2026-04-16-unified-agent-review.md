# Unified Health Agent — Code Review 改进清单

## 概述

对统一健康 Agent 的 5 个核心文件进行了全面 review，发现 1 个 CRITICAL、3 个 HIGH、11 个 MEDIUM、15 个 LOW 级别问题。

---

## CRITICAL（必须立即修复）

### 1. Safety Guardian 内联检查完全失效
- **文件**: `agent_executor.py` line 147-155
- **问题**: `from app.agents.safety_guardian.guardian import SafetyGuardian` — 这个类不存在。模块只导出 `evaluate_safety(twin)` 函数。调用签名 `guardian.evaluate(self.db, user_id)` 也完全错误。被 `except: pass` 静默吞掉，安全检查从未执行过。
- **修复**: 改用正确的导入和调用链：
  ```python
  from app.twin.builder import build_twin
  from app.agents.safety_guardian import evaluate_safety
  twin = build_twin(self.db, user_id)
  report = evaluate_safety(twin)
  critical = [a for a in report.alerts if a.severity >= 3]
  ```

---

## HIGH（尽快修复）

### 2. 硬编码生产 URL
- **文件**: `agent_executor.py` line 398
- **问题**: `base_url = "https://health.executor.life/api"` 硬编码。开发/测试环境也会打到生产 API。
- **修复**: 从 `settings` 读取，或通过请求上下文派生。

### 3. Safety 失败被静默吞掉
- **文件**: `agent_executor.py` line 155
- **问题**: `except Exception: pass` — 安全检查失败不记日志。即使修了 Issue 1，后续的异常也会被静默忽略。
- **修复**: 改为 `except Exception as e: logger.warning(f"Safety check failed: {e}")`

### 4. 无请求体大小限制
- **文件**: `agent.py` AgentRequest
- **问题**: `image_base64` 和 `file_base64` 无长度校验，可以传入 GB 级 payload。
- **修复**: Pydantic validator 限制 image_base64 最大 10MB（~13MB base64）。

---

## MEDIUM（应该修复）

### 5. 日期默认值使用服务器本地时间
- **文件**: `agent_executor.py` line 479, 552
- **问题**: `datetime.now().strftime("%Y-%m-%d")` 使用服务器时区（UTC），不是用户时区（Asia/Shanghai）。凌晨 0-8 点间日期会差一天。
- **修复**: 使用 `get_china_today()` 或 `datetime.now(timezone(timedelta(hours=8)))`。

### 6. 补剂名称匹配失败时静默 fallback
- **文件**: `agent_executor.py` line 533-537
- **问题**: 补剂查找 JSON 解析失败时 `except Exception: pass`，然后 fallback 到 `/supplements/records` POST，但此时 data 可能缺少 `supplement_id`，导致写入失败或脏数据。
- **修复**: `except` 块返回明确错误信息。

### 7. 用药记录空名称无错误提示
- **文件**: `agent_executor.py` line 540-560
- **问题**: `medication` 类型但 `med_name` 为空时，代码跳过整个 `if med_name:` 块，最终返回 "不支持的记录类型 medication"，误导用户。
- **修复**: 空名称时返回 "需要提供药物名称"。

### 8. 症状记录硬编码 profile_id=1
- **文件**: `agent_executor.py` line 572
- **问题**: `data.get("profile_id", 1)` — 用户可能没有 id=1 的疾病档案。
- **修复**: profile_id 缺失时返回错误或查找用户的第一个 profile。

### 9. API 响应截断破坏 JSON
- **文件**: `agent_executor.py` line 669-671
- **问题**: `text[:3000]` 截断可能在 JSON 中间切断，产生非法 JSON 给 LLM。
- **修复**: 先解析 JSON，限制数组长度，再序列化回去。

### 10. 前端 handleInlineSend 不处理 error 事件
- **文件**: `useChat.ts` handleInlineSend
- **问题**: inline 模式只处理 token/tool_call/tool_result/done 事件，error 事件被忽略，用户看到永远 loading。
- **修复**: 增加 `event.event === 'error'` 处理。

### 11. handleDoneEvent 对 Agent 响应无效
- **文件**: `useChat.ts` handleDoneEvent
- **问题**: 该函数查找 `result.diet_saved`、`result.workout_analysis` 等字段，但 Agent done 事件只有 `conversation_id/message_id/elapsed_ms/mode`。饮食通知、运动分析通知在 Agent 路径下丢失。
- **修复**: Agent 执行写操作后，在 done 事件中附加相关通知数据。

### 12. 文件附件只记文本标记，不传给 LLM
- **文件**: `agent_executor.py` line 63-64, 73-83
- **问题**: `file_base64`/`file_name` 只加了 `[附件: filename]` 文本标记，LLM 完全看不到文件内容。
- **修复**: 图片文件走多模态；PDF 提取文本注入消息。

### 13. 前端无 AbortController 取消支持
- **文件**: `ai.ts` agentApi.streamMessage
- **问题**: 用户切换对话或导航离开时无法取消进行中的 fetch 流。
- **修复**: 接受可选 AbortSignal 参数。

---

## LOW（可选优化）

### 14. 重复 `import json as _json`
- `agent_executor.py` line 453, 522, 546 — 顶层已导入 `json`，无需重命名导入。

### 15. httpx.AsyncClient 每次调用新建
- `_api_get`/`_api_post`/`_api_patch` 每次创建新 client。Agent 一轮可能 5+ 次 HTTP 调用。
- **改进**: 在 `run_stream` 开始时创建共享 client，结束时关闭。

### 16. `_call_llm_direct` 每次重试新建 client
- line 344 — 同 Issue 15。移到循环外。

### 17. 基因指标查询未实现 indicator 过滤
- tool schema 说 indicator 用于 medical_exam 和 genetic，但代码只过滤了 medical_exam。

### 18. health_query 描述未提及 medical_exam/genetic/medication
- tool description 说"步数、心率…等"，没明确提到可以查体检/基因/用药。LLM 可能不知道用这些 dimension。

### 19. supplement_guide 工具无 `required: []`
- 空参数对象缺少 `required` 字段，部分模型可能困惑。

### 20. health_record data 字段无结构化 properties
- `data` 是泛型 object，LLM 全靠 description 里的示例来猜字段名。容易出错（如 `weight_kg` vs `weight`）。

### 21. setTimeout 长延时提醒不可靠
- `useChat.ts` line 66 — 60 分钟的 setTimeout 在浏览器后台 tab 中不可靠。

### 22. 消息 ID 用 Date.now() 可能冲突
- 快速连续发送时 ID 可能重复。

### 23. Timer 泄漏
- `useChat.ts` — catch/finally 块未清理 waitTimer/waitTimer2/buf.timer。

---

## 优先执行顺序

| 优先级 | Issue | 预期修复时间 |
|--------|-------|-------------|
| P0 | #1 Safety 导入修复 | 5 分钟 |
| P0 | #3 Safety 日志 | 1 分钟 |
| P1 | #2 硬编码 URL | 10 分钟 |
| P1 | #5 时区修复 | 5 分钟 |
| P1 | #4 请求体大小限制 | 5 分钟 |
| P1 | #6 补剂 fallback 错误处理 | 5 分钟 |
| P1 | #7 用药空名称处理 | 2 分钟 |
| P2 | #9 JSON 截断修复 | 15 分钟 |
| P2 | #10 inline error 处理 | 5 分钟 |
| P2 | #11 Agent done 事件增强 | 15 分钟 |
| P2 | #15 共享 httpx client | 10 分钟 |
| P3 | 其余 LOW 级别 | 各 2-5 分钟 |
