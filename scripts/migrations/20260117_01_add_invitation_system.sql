-- 邀请码系统迁移脚本
-- 日期: 2026-01-17
-- 描述: 添加邀请码和用户申请表，实现私域用户注册体系

-- 1. 创建邀请码表
CREATE TABLE IF NOT EXISTS invitation_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(32) UNIQUE NOT NULL,
    created_by INTEGER REFERENCES users(id),
    note VARCHAR(200),
    max_uses INTEGER DEFAULT 1,
    used_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_invitation_codes_code ON invitation_codes(code);
CREATE INDEX IF NOT EXISTS idx_invitation_codes_created_by ON invitation_codes(created_by);

-- 2. 创建用户申请表
CREATE TABLE IF NOT EXISTS user_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    invitation_code_id INTEGER NOT NULL REFERENCES invitation_codes(id),
    health_questionnaire TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_note TEXT,
    user_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_user_applications_email ON user_applications(email);
CREATE INDEX IF NOT EXISTS idx_user_applications_status ON user_applications(status);
CREATE INDEX IF NOT EXISTS idx_user_applications_invitation_code_id ON user_applications(invitation_code_id);

-- 3. 为管理员创建初始邀请码（用于测试）
-- 注意: 这是一个示例，实际使用时应该通过管理后台生成
INSERT INTO invitation_codes (code, note, max_uses, is_active)
SELECT 'EXECUTOR2026', '初始管理员邀请码', 10, 1
WHERE NOT EXISTS (SELECT 1 FROM invitation_codes WHERE code = 'EXECUTOR2026');

-- 4. 确保 users 表有必要的字段
-- (这些字段在原模型中已存在，这里做兼容性检查)
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT 0;
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_code VARCHAR(32);
