import sqlite3

# Connect to your database
conn = sqlite3.connect('database.db')  # Replace with your actual DB name
cursor = conn.cursor()

# Create the attendance table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL
    )
''')

# Create the users table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        daily_rate REAL NOT NULL
    )
''')

# Create the payroll table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS payroll (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        salary REAL NOT NULL,
        pay_date TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
''')

# Connect to your SQLite database (change the filename if yours is different)
conn = sqlite3.connect('database.db')  # or 'instance/database.db' if it's in a folder
c = conn.cursor()  # <-- Define the cursor here

# Create the attendance table
c.execute('''
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL
)
''')


cursor.execute('''
CREATE TABLE leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    start TEXT,
    end TEXT,
    type TEXT,
    reason TEXT,
    status TEXT DEFAULT 'Pending',
    rejection_reason TEXT
)
''')

cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

# Commit the changes and close the connection
conn.commit()
conn.close()

print("✅ Database and tables created.")
