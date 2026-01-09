-- 创建统一设备凭证表
-- 支持多种智能设备的认证信息存储

CREATE TABLE IF NOT EXISTS device_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    
    -- 设备类型: garmin, huawei, apple, xiaomi, fitbit
    device_type VARCHAR(50) NOT NULL,
    
    -- 认证类型: password, oauth2, token, file
    auth_type VARCHAR(20) NOT NULL DEFAULT 'password',
    
    -- 账号密码认证 (Garmin): 加密的 JSON {"email": "...", "password": "..."}
    encrypted_credentials TEXT,
    
    -- OAuth 2.0 认证 (华为、Fitbit): 加密存储
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at DATETIME,
    oauth_scope VARCHAR(500),
    
    -- 设备特定配置: JSON {"is_cn": true, "region": "CN"}
    config TEXT,
    
    -- 状态
    is_valid BOOLEAN DEFAULT 1,
    sync_enabled BOOLEAN DEFAULT 1,
    last_sync_at DATETIME,
    last_error TEXT,
    error_count INTEGER DEFAULT 0,
    
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    
    -- 外键
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_device_credentials_user_id ON device_credentials(user_id);
CREATE INDEX IF NOT EXISTS ix_device_credentials_device_type ON device_credentials(device_type);

-- 复合唯一约束：同一用户同一设备类型只能有一条记录
CREATE UNIQUE INDEX IF NOT EXISTS uq_device_credentials_user_device 
ON device_credentials(user_id, device_type);

-- 添加说明
-- 此表用于统一管理多种智能设备的认证信息，包括：
-- 1. Garmin: 使用 encrypted_credentials 存储加密的账号密码
-- 2. 华为手表: 使用 access_token/refresh_token 存储 OAuth Token
-- 3. Apple Watch: 主要通过文件导入，可能不需要凭证
-- 4. 小米手环: OAuth Token
-- 5. Fitbit: OAuth Token
