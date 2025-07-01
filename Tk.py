import sqlite3

# Connect to your SQLite database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# DROP the old table if it exists (optional but safe for testing)
cursor.execute('DROP TABLE IF EXISTS leave_requests')
# Commit the changes and close the connection
conn.commit()
conn.close()