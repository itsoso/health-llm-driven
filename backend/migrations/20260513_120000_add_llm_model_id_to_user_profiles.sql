-- 用户级 LLM 偏好 (2026-05-13)
-- 加列 llm_model_id, NULL = fallback admin global / settings 默认
-- model_id 取自 app/services/llm/model_registry.py (gpt-4o-mini / qwen3.6-plus / ...)

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS llm_model_id VARCHAR(50);
