-- 补剂联盟产品目录
CREATE TABLE IF NOT EXISTS affiliate_products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    brand VARCHAR(100),
    image_url VARCHAR(500),
    supplement_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'basic',
    keywords JSONB DEFAULT '[]',
    platform VARCHAR(50) NOT NULL DEFAULT 'iherb',
    affiliate_url VARCHAR(500) NOT NULL,
    price_display VARCHAR(50),
    currency VARCHAR(10) DEFAULT 'CNY',
    gene_tags JSONB DEFAULT '[]',
    gene_description VARCHAR(200),
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_affiliate_products_supplement ON affiliate_products(supplement_name);
CREATE INDEX IF NOT EXISTS ix_affiliate_products_category ON affiliate_products(category);
CREATE INDEX IF NOT EXISTS ix_affiliate_products_platform ON affiliate_products(platform);
CREATE INDEX IF NOT EXISTS ix_affiliate_products_active ON affiliate_products(is_active);
