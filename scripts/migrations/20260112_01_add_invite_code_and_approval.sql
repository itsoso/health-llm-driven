-- 添加邀请码和审核状态字段
ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN invite_code TEXT;

-- 将现有用户标记为已审核（兼容旧数据）
UPDATE users SET is_approved = TRUE WHERE is_approved IS NULL OR is_approved = FALSE;

-- 为管理员用户设置已审核状态
UPDATE users SET is_approved = TRUE WHERE is_admin = TRUE;
