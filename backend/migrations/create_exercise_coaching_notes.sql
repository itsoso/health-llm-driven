CREATE TABLE IF NOT EXISTS exercise_coaching_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exercise_type VARCHAR(50) NOT NULL,
    title VARCHAR(200),
    good_points TEXT,
    issues TEXT,
    checklist TEXT,
    source_type VARCHAR(30) DEFAULT 'ai_video',
    video_url VARCHAR(500),
    frame_urls TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_coaching_user_exercise ON exercise_coaching_notes(user_id, exercise_type);
