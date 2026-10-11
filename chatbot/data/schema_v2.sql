-- Bổ sung vào schema v1; các bảng cũ giữ nguyên và giữ ID.
CREATE TABLE IF NOT EXISTS database_metadata (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
    payload TEXT NOT NULL, source TEXT NOT NULL, is_demo INTEGER NOT NULL CHECK(is_demo=1),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_variants (
    id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
    size TEXT NOT NULL, price_vnd INTEGER CHECK(price_vnd IS NULL OR (typeof(price_vnd)='integer' AND price_vnd>=0)),
    servings INTEGER CHECK(servings IS NULL OR servings>0),
    stock_quantity INTEGER CHECK(stock_quantity IS NULL OR (typeof(stock_quantity)='integer' AND stock_quantity>=0)),
    stock_status TEXT NOT NULL CHECK(stock_status IN ('in_stock','out_of_stock','preorder','unknown')),
    UNIQUE(product_id,size)
);
CREATE TABLE IF NOT EXISTS toppings (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, price_vnd INTEGER NOT NULL CHECK(typeof(price_vnd)='integer' AND price_vnd>=0),
    allergen TEXT NOT NULL, is_demo INTEGER NOT NULL CHECK(is_demo=1)
);
CREATE TABLE IF NOT EXISTS product_toppings (
    product_id TEXT NOT NULL REFERENCES products(id), topping_id TEXT NOT NULL REFERENCES toppings(id),
    PRIMARY KEY(product_id,topping_id)
);
CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL, version TEXT NOT NULL,
    is_demo INTEGER NOT NULL CHECK(is_demo=1), source TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS business_settings (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL, version TEXT NOT NULL, is_demo INTEGER NOT NULL CHECK(is_demo=1)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL
);
-- orders mở rộng submissions demo cùng ID, không tạo một đơn kinh doanh thứ hai.
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY REFERENCES submissions(id), conversation_id TEXT NOT NULL REFERENCES conversations(id),
    code TEXT NOT NULL UNIQUE, idempotency_key TEXT NOT NULL UNIQUE,
    draft_id TEXT NOT NULL REFERENCES drafts(id), revision INTEGER NOT NULL,
    total_vnd INTEGER NOT NULL CHECK(typeof(total_vnd)='integer' AND total_vnd>=0),
    status TEXT NOT NULL CHECK(status='DEMO_CONFIRMED'), payment_status TEXT NOT NULL CHECK(payment_status='unpaid'),
    is_demo INTEGER NOT NULL CHECK(is_demo=1), source TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
    product_id TEXT, variant_id TEXT, quantity INTEGER NOT NULL CHECK(quantity>0),
    snapshot TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_owner ON messages(conversation_id,id);
CREATE INDEX IF NOT EXISTS orders_owner ON orders(conversation_id,created_at);
CREATE INDEX IF NOT EXISTS variants_product ON product_variants(product_id);
