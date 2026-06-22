-- P4 锻炼链 opt-in 开关:user_profiles.workout_chain_enabled。
-- additive、幂等可重跑;NULL = 旧行为(单锻炼项),不影响既有用户。
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS workout_chain_enabled BOOLEAN;
