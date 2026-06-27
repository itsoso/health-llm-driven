-- PR3 supplement ingredient spine. Test databases use ORM create_all, this is for SQLite dev DBs.
CREATE TABLE IF NOT EXISTS supplement_ingredients (
    ingredient_id VARCHAR(120) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    aliases JSON NOT NULL DEFAULT '[]',
    ul_amount REAL,
    ul_unit VARCHAR(40),
    source VARCHAR(80) NOT NULL,
    source_ref VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_supplement_ingredients_canonical_name
    ON supplement_ingredients (canonical_name);
CREATE INDEX IF NOT EXISTS ix_supplement_ingredients_active
    ON supplement_ingredients (is_active);
