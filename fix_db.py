import sqlite3

conn = sqlite3.connect("learnify.db")
c = conn.cursor()

try:
    c.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0;")
    print("✔ banned column added successfully!")
except Exception as e:
    print("✔ Column already exists or error:", e)

conn.commit()
conn.close()
