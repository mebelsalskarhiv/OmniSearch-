-- Инициализация базы данных PostgreSQL для OmniSearch

-- Включаем расширение для триграммного поиска
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Таблица товаров
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(500) NOT NULL,
    article VARCHAR(100) UNIQUE,
    barcode VARCHAR(50) UNIQUE,
    category VARCHAR(200),
    brand VARCHAR(200),
    description TEXT,
    attributes JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Таблица магазинов
CREATE TABLE IF NOT EXISTS shops (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    url VARCHAR(500),
    address TEXT,
    rating REAL CHECK (rating >= 0 AND rating <= 5)
);

-- Таблица связей товаров и магазинов (цены, наличие)
CREATE TABLE IF NOT EXISTS shop_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES products(id),
    shop_id UUID REFERENCES shops(id),
    price DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'RUB',
    availability VARCHAR(50),
    url VARCHAR(1000),
    last_updated TIMESTAMPTZ DEFAULT now(),
    UNIQUE(product_id, shop_id)
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_products_article ON products(article);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);

-- Индексы для shop_products
CREATE INDEX IF NOT EXISTS idx_shop_products_product ON shop_products(product_id);
CREATE INDEX IF NOT EXISTS idx_shop_products_shop ON shop_products(shop_id);
CREATE INDEX IF NOT EXISTS idx_shop_products_price ON shop_products(price);

-- Пример данных (опционально)
INSERT INTO shops (name, url, rating) VALUES 
    ('Test Shop 1', 'https://example.com/shop1', 4.5),
    ('Test Shop 2', 'https://example.com/shop2', 4.2)
ON CONFLICT DO NOTHING;
