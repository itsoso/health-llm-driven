-- PR1 food nutrition spine: reviewed food identity + per-100g nutrient facts.
CREATE TABLE IF NOT EXISTS food_items (
    food_id VARCHAR(120) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    locale VARCHAR(20) NOT NULL DEFAULT 'zh-CN',
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS food_nutrients (
    food_id VARCHAR(120) PRIMARY KEY REFERENCES food_items(food_id) ON DELETE CASCADE,
    kcal_per_100g DOUBLE PRECISION,
    protein_g_per_100g DOUBLE PRECISION,
    carbs_g_per_100g DOUBLE PRECISION,
    fat_g_per_100g DOUBLE PRECISION,
    fiber_g_per_100g DOUBLE PRECISION,
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);

ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS food_id VARCHAR(120);
ALTER TABLE diet_records ADD COLUMN IF NOT EXISTS source VARCHAR(80);

CREATE INDEX IF NOT EXISTS ix_food_items_canonical_name ON food_items (canonical_name);
CREATE INDEX IF NOT EXISTS ix_food_items_active ON food_items (is_active);
CREATE INDEX IF NOT EXISTS idx_diet_food_id ON diet_records (food_id);
