-- 迁移: 添加微信小程序用户字段
-- 日期: 2026-01-08
-- 说明: 支持微信小程序登录

-- 微信 OpenID（唯一标识）
ALTER TABLE users ADD COLUMN wechat_openid VARCHAR UNIQUE;

-- 微信 UnionID（多平台统一标识）
ALTER TABLE users ADD COLUMN wechat_unionid VARCHAR;

-- 微信会话密钥
ALTER TABLE users ADD COLUMN wechat_session_key VARCHAR;

-- 头像 URL
ALTER TABLE users ADD COLUMN avatar_url VARCHAR;

-- 手机号
ALTER TABLE users ADD COLUMN phone VARCHAR;

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_users_wechat_openid ON users(wechat_openid);
CREATE INDEX IF NOT EXISTS ix_users_wechat_unionid ON users(wechat_unionid);

