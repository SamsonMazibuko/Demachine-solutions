import sqlite3

DB_PATH = 'instance/database.db'
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Add email_notifications if not exists
c.execute("PRAGMA table_info(user);")
columns = [row[1] for row in c.fetchall()]
if 'email_notifications' not in columns:
    c.execute("ALTER TABLE user ADD COLUMN email_notifications BOOLEAN DEFAULT 1;")
    print("Added column 'email_notifications' to user table.")
else:
    print("Column 'email_notifications' already exists.")

if 'sms_notifications' not in columns:
    c.execute("ALTER TABLE user ADD COLUMN sms_notifications BOOLEAN DEFAULT 0;")
    print("Added column 'sms_notifications' to user table.")
else:
    print("Column 'sms_notifications' already exists.")

conn.commit()
conn.close() 