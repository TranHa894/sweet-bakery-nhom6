import sqlite3

# Connect to the database (creates the file if it doesn't exist)
conn = sqlite3.connect('orders.db')

# Create a cursor object to execute SQL commands
cursor = conn.cursor()

# Execute a SQL command to create a table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE
    )
''')

# Save (commit) the changes and close the connection
conn.commit()
conn.close()

print("Database and table created successfully!")