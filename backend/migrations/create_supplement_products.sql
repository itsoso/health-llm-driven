-- 补剂产品库表
CREATE TABLE IF NOT EXISTS supplement_products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    description TEXT,
    serving_size VARCHAR(100),
    servings_per_container INTEGER,
    container_count INTEGER,
    ingredients JSONB DEFAULT '[]'::jsonb,
    price_cny NUMERIC(10,2),
    price_per_serving NUMERIC(10,2),
    currency VARCHAR(10) DEFAULT 'CNY',
    purchase_url VARCHAR(500),
    platform VARCHAR(50) DEFAULT 'iherb',
    image_url VARCHAR(500),
    certifications JSONB DEFAULT '[]'::jsonb,
    capsule_type VARCHAR(30),
    usage_advice TEXT,
    precautions TEXT,
    gene_relevance JSONB DEFAULT '[]'::jsonb,
    health_tags JSONB DEFAULT '[]'::jsonb,
    rating NUMERIC(3,1),
    review_count INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_supplement_products_brand ON supplement_products(brand);
CREATE INDEX IF NOT EXISTS idx_supplement_products_category ON supplement_products(category);

-- 给现有 supplement_definitions 表增加 product_id 外键
ALTER TABLE supplement_definitions
    ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES supplement_products(id);
