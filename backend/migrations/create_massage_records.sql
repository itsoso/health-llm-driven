-- 按摩/理疗记录表
CREATE TABLE IF NOT EXISTS massage_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    record_date DATE NOT NULL,
    start_time VARCHAR(5),
    duration_minutes INTEGER,
    location_name VARCHAR(200),
    location_address VARCHAR(500),
    massage_type VARCHAR(50) DEFAULT '推拿',
    therapist VARCHAR(100),
    body_parts VARCHAR(500),
    price FLOAT,
    issues_before TEXT,
    treatment_notes TEXT,
    feeling_after TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_massage_records_user_date ON massage_records(user_id, record_date);
