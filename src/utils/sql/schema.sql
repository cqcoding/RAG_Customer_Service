-- Store database schema.
-- The COMMENT ON statements are read back by the SQL agent at runtime
-- (see src/utils/sql_database.py), so keep them accurate: they are the
-- agent's only documentation of what each column means.

DROP TABLE IF EXISTS order_items, promotions, orders, products, customers, categories CASCADE;

CREATE TABLE categories (
    category_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT
);
COMMENT ON TABLE categories IS 'Product categories of the music store (e.g. Guitarras, Violões, Ukuleles).';

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT,
    email        TEXT,
    city         TEXT
);
COMMENT ON TABLE customers IS 'Registered customers. Only customer_id and city are readable: personal data is not accessible.';
COMMENT ON COLUMN customers.phone IS 'Format: (DD) 9XXXX-XXXX';

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    price_brl       NUMERIC(10, 2) NOT NULL,
    name            TEXT NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories (category_id),
    description     TEXT,
    stock_quantity  INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    specs           JSONB,
    created_at      DATE
);
COMMENT ON TABLE products IS 'Product catalog. Base price before any promotion.';
COMMENT ON COLUMN products.price_brl IS 'Full price in BRL, without discounts.';
COMMENT ON COLUMN products.status IS 'One of: active (for sale), discontinued (no longer sold), coming_soon (not yet available).';
COMMENT ON COLUMN products.specs IS 'JSONB of technical specs. Keys vary by product, e.g. top, back_sides, neck, strings, scale, electronics, color. Query with specs->>''key''.';

CREATE TABLE orders (
    order_id            INTEGER PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date          DATE NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
    total_brl           NUMERIC(10, 2) NOT NULL,
    payment_method      TEXT NOT NULL,
    tracking_code       TEXT,
    estimated_delivery  DATE,
    notes               TEXT
);
COMMENT ON TABLE orders IS 'Customer orders. Line items are in order_items.';
COMMENT ON COLUMN orders.status IS 'One of: pending (awaiting payment), confirmed (paid, not shipped), shipped, delivered, cancelled.';
COMMENT ON COLUMN orders.total_brl IS 'Amount actually charged for the order, in BRL.';
COMMENT ON COLUMN orders.payment_method IS 'One of: pix, boleto, debit, credit_Nx where N is the number of installments (e.g. credit_12x).';
COMMENT ON COLUMN orders.tracking_code IS 'Carrier tracking code. NULL until the order is shipped.';
COMMENT ON COLUMN orders.estimated_delivery IS 'NULL until the order is shipped.';
COMMENT ON COLUMN orders.notes IS 'Free text, mostly the cancellation reason. Usually NULL.';

CREATE TABLE order_items (
    order_id    INTEGER NOT NULL REFERENCES orders (order_id),
    product_id  INTEGER NOT NULL REFERENCES products (product_id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);
COMMENT ON TABLE order_items IS 'Products in each order. Join orders -> order_items -> products.';

CREATE TABLE promotions (
    promotion_id      INTEGER PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products (product_id),
    discount_percent  INTEGER NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
    description       TEXT,
    is_active         BOOLEAN NOT NULL
);
COMMENT ON TABLE promotions IS 'Product discounts. Only rows with is_active = TRUE apply now; inactive rows are past campaigns.';
COMMENT ON COLUMN promotions.discount_percent IS 'Discounted price = products.price_brl * (1 - discount_percent / 100.0).';

