import sqlite3

# Connect to the database (creates the file if it doesn't exist)
conn = sqlite3.connect('orders.db')

# Create a cursor object to execute SQL commands
cursor = conn.cursor()

cursor.executescript('''
    CREATE TABLE IF NOT EXISTS order_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        phone_number INTEGER UNIQUE NOT NULL,
        address TEXT NOT NULL,
        delivery_date DATETIME,
        created_date DATETIME,
        note TEXT,
        status TEXT DEFAULT 'Pending'
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price INTEGER NOT NULL,
        stock_quantity INTEGER NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        price_at_purchase INTEGER,
        FOREIGN KEY (order_id) REFERENCES order_info(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );
''')

# Save (commit) the changes and close the connection
conn.commit()
conn.close()

print("Database and table created successfully!")
