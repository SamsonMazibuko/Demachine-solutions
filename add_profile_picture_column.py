import sqlite3

DB_PATH = 'instance/database.db'
COLUMN_NAME = 'profile_picture'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check if the column already exists
c.execute("PRAGMA table_info(user);")
columns = [row[1] for row in c.fetchall()]
if COLUMN_NAME not in columns:
    c.execute(f"ALTER TABLE user ADD COLUMN {COLUMN_NAME} VARCHAR(255);")
    print(f"Added column '{COLUMN_NAME}' to user table.")
else:
    print(f"Column '{COLUMN_NAME}' already exists.")

conn.commit()
conn.close() 