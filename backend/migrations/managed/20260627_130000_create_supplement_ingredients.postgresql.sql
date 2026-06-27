-- PR3 supplement ingredient spine: reviewed supplement identity + UL facts.
CREATE TABLE IF NOT EXISTS supplement_ingredients (
    ingredient_id VARCHAR(120) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    ul_amount DOUBLE PRECISION,
    ul_unit VARCHAR(40),
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_supplement_ingredients_canonical_name
    ON supplement_ingredients (canonical_name);
CREATE INDEX IF NOT EXISTS ix_supplement_ingredients_active
    ON supplement_ingredients (is_active);
