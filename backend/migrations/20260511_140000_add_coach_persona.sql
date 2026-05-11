-- Phase 3 P3-1: User.coach_persona — Coach Persona 三档
-- (strict_coach / gentle_advisor / data_driven)
-- orchestrator 合成时按 persona 切语气, 不影响 specialist 逻辑.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS coach_persona VARCHAR(20) DEFAULT 'gentle_advisor';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_coach_persona'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT chk_users_coach_persona
            CHECK (coach_persona IS NULL OR coach_persona IN
                   ('strict_coach', 'gentle_advisor', 'data_driven'));
    END IF;
END $$;

COMMENT ON COLUMN users.coach_persona IS 'P3-1 Coach Persona: strict_coach=严厉教练 / gentle_advisor=温和顾问(默认) / data_driven=数据派. Orchestrator 按 persona 切 LLM 合成语气.';
