CREATE TABLE IF NOT EXISTS users (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    city  VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO users (name, email, city) VALUES
    ('Priya Sharma',  'priya@example.com',  'Mumbai'),
    ('Rahul Gupta',   'rahul@example.com',  'Delhi'),
    ('Ananya Patel',  'ananya@example.com', 'Bangalore'),
    ('Vikram Singh',  'vikram@example.com', 'Chennai'),
    ('Sneha Reddy',   'sneha@example.com',  'Hyderabad')
ON CONFLICT (email) DO NOTHING;

CREATE TABLE IF NOT EXISTS orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    product    VARCHAR(200) NOT NULL,
    amount     DECIMAL(10,2),
    status     VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO orders (user_id, product, amount, status) VALUES
    (1, 'MacBook Pro',    120000.00, 'delivered'),
    (2, 'iPhone 15',       85000.00, 'shipped'),
    (3, 'AirPods Pro',     20000.00, 'pending'),
    (1, 'iPad Air',        65000.00, 'delivered'),
    (4, 'Apple Watch',     45000.00, 'cancelled');