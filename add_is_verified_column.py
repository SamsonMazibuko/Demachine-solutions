import sqlite3

DB_PATH = 'instance/database.db'
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("PRAGMA table_info(user);")
columns = [row[1] for row in c.fetchall()]
if 'is_verified' not in columns:
    c.execute("ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0;")
    print("Added column 'is_verified' to user table.")
else:
    print("Column 'is_verified' already exists.")

conn.commit()
conn.close() 