-- PR1 food nutrition spine. Test databases use ORM create_all; this is for SQLite dev DBs.
CREATE TABLE IF NOT EXISTS food_items (
    food_id VARCHAR(120) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    aliases JSON NOT NULL DEFAULT '[]',
    locale VARCHAR(20) NOT NULL DEFAULT 'zh-CN',
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS food_nutrients (
    food_id VARCHAR(120) PRIMARY KEY,
    kcal_per_100g REAL,
    protein_g_per_100g REAL,
    carbs_g_per_100g REAL,
    fat_g_per_100g REAL,
    fiber_g_per_100g REAL,
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY(food_id) REFERENCES food_items(food_id) ON DELETE CASCADE
);

ALTER TABLE diet_records ADD COLUMN food_id VARCHAR(120);
ALTER TABLE diet_records ADD COLUMN source VARCHAR(80);

CREATE INDEX IF NOT EXISTS ix_food_items_canonical_name ON food_items (canonical_name);
CREATE INDEX IF NOT EXISTS ix_food_items_active ON food_items (is_active);
CREATE INDEX IF NOT EXISTS idx_diet_food_id ON diet_records (food_id);
