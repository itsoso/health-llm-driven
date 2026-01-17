-- 为 user_applications 表添加 hashed_password 字段
-- 日期: 2026-01-17
-- 描述: 保存用户注册时的密码，审批时使用

ALTER TABLE user_applications ADD COLUMN hashed_password TEXT;
