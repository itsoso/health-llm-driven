-- 跑步动态指导 (Live Run Coach) 会话表
-- 创建时间: 2026-05-12
-- 用途:
--   跑步中实时配速/心率监控 + 规则触发 + 语音提示
--   跑后 LLM narrative 复盘 (基于 events + GPS samples)
--
-- V1 约束:
--   - 目标配速、Z4 上限由跑前 readiness + 历史训练算出
--   - 3 条硬规则 (配速偏离 / 心率过载 / 总量超限) 全在 mobile 本地执行
--   - events JSON 存 in-session 提示, 不另开 live_run_events 表

CREATE TABLE IF NOT EXISTS live_run_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    -- 跑前目标 (用户选 or specialist 推荐)
    target_pace_seconds INTEGER,          -- 目标配速 (秒/公里), 例如 330 = 5:30
    target_label VARCHAR,                  -- easy / tempo / fast / custom
    max_z4_minutes INTEGER,              -- 今日 Z4+ 累计上限 (recovery_coach 输入)
    readiness_score INTEGER,                -- 跑前 readiness 快照 0-100

    -- 跑
    total_distance_m FLOAT DEFAULT 0.0,
    total_duration_s INTEGER DEFAULT 0,
    avg_pace_seconds INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    z4_plus_minutes FLOAT DEFAULT 0.0,
    calories INTEGER,

    -- 事件列表: [{ts, rule_id, message, metric_snapshot}]
    events JSONB DEFAULT '[]',

    -- GPS 抽样轨迹: [{ts, lat, lon, pace, hr}], 每 30s 一个点
    gps_samples JSONB DEFAULT '[]',

    -- 跑后 LLM 复盘
    narrative TEXT,
    narrative_status VARCHAR DEFAULT 'pending',  -- pending / done / failed

    -- 元数据
    source VARCHAR DEFAULT 'mobile',           -- mobile / siri / watch
    aborted BOOLEAN DEFAULT FALSE,
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_live_run_user_started ON live_run_sessions(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_live_run_narrative_status ON live_run_sessions(narrative_status);
