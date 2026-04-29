-- ────────────────────────────────────────────────────────────────────
-- 断舍离: 删除支线业务表 (2026-04-28)
--
-- 此迁移一并执行:
-- - Kids: kids_pet_profiles / kids_daily_plans / vocabulary_words
-- - Security-Life: 6 张
-- - Trip: trips / trip_items
-- - Massage: massage_records
-- - Social: friendships / pk_challenges / challenge_participants /
--           group_chats / group_members / group_messages / direct_messages
-- - 成就: badge_definitions / user_badges
-- - News: news_articles / news_api_keys / news_comments
-- - 外部建议: external_recommendations
-- - 联盟产品: affiliate_products
-- - users.kids_points 列移除
--
-- 安全: 所有删除表都没有 surviving 表 FK 指向它们（已依赖扫描确认）.
-- 唯一 soft link: pk_challenges.checkin_template_id → checkin_templates.id
-- 会随 pk_challenges 表一起消失, checkin_templates 保留.
--
-- 执行前请备份: pg_dump $DATABASE_URL > pre-cleanup-$(date +%Y%m%d).sql
-- ────────────────────────────────────────────────────────────────────

BEGIN;

-- Kids
DROP TABLE IF EXISTS kids_pet_profiles CASCADE;
DROP TABLE IF EXISTS kids_daily_plans CASCADE;
DROP TABLE IF EXISTS vocabulary_words CASCADE;

-- Security Life
DROP TABLE IF EXISTS security_life_assets CASCADE;
DROP TABLE IF EXISTS security_life_profiles CASCADE;
DROP TABLE IF EXISTS security_life_properties CASCADE;
DROP TABLE IF EXISTS security_life_baskets CASCADE;
DROP TABLE IF EXISTS security_life_cash_layers CASCADE;
DROP TABLE IF EXISTS security_life_checklist_items CASCADE;
DROP TABLE IF EXISTS security_life_red_lines CASCADE;

-- Trip
DROP TABLE IF EXISTS trip_items CASCADE;
DROP TABLE IF EXISTS trips CASCADE;

-- Massage
DROP TABLE IF EXISTS massage_records CASCADE;

-- Social
DROP TABLE IF EXISTS challenge_participants CASCADE;
DROP TABLE IF EXISTS pk_challenges CASCADE;
DROP TABLE IF EXISTS friendships CASCADE;
DROP TABLE IF EXISTS group_messages CASCADE;
DROP TABLE IF EXISTS group_members CASCADE;
DROP TABLE IF EXISTS group_chats CASCADE;
DROP TABLE IF EXISTS direct_messages CASCADE;

-- Achievements / Points
DROP TABLE IF EXISTS user_badges CASCADE;
DROP TABLE IF EXISTS badge_definitions CASCADE;

-- News
DROP TABLE IF EXISTS news_comments CASCADE;
DROP TABLE IF EXISTS news_articles CASCADE;
DROP TABLE IF EXISTS news_api_keys CASCADE;

-- External recommendations
DROP TABLE IF EXISTS external_recommendations CASCADE;

-- Affiliate products
DROP TABLE IF EXISTS affiliate_products CASCADE;

-- User 表: 删 kids_points 列 (产品已移除 kids 模式)
ALTER TABLE users DROP COLUMN IF EXISTS kids_points;

COMMIT;
