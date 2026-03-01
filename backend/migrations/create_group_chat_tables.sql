-- 群聊表
CREATE TABLE IF NOT EXISTS group_chats (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    creator_id  INTEGER NOT NULL REFERENCES users(id),
    avatar_url  VARCHAR,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

-- 群成员表
CREATE TABLE IF NOT EXISTS group_members (
    id          SERIAL PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    role        VARCHAR(20) DEFAULT 'member',
    joined_at   TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_group_member UNIQUE (group_id, user_id)
);

-- 群消息表
CREATE TABLE IF NOT EXISTS group_messages (
    id          SERIAL PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
    sender_id   INTEGER NOT NULL REFERENCES users(id),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_group_members_user    ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_group_messages_group  ON group_messages(group_id, created_at DESC);
