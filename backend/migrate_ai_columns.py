"""
Run this script ONCE to add AI columns to your existing database.
Usage: python migrate_ai_columns.py

If you prefer, you can just delete jobradar.db and restart — the columns
are also added to the main schema in database.py (see PATCH_INSTRUCTIONS).
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "jobradar.db")

if not os.path.exists(db_path):
    print("No database found — it will be created with AI columns on next startup.")
    exit(0)

conn = sqlite3.connect(db_path)

# Check if columns already exist
cursor = conn.execute("PRAGMA table_info(jobs)")
columns = [row[1] for row in cursor.fetchall()]

added = []

if "ai_score" not in columns:
    conn.execute("ALTER TABLE jobs ADD COLUMN ai_score INTEGER DEFAULT NULL")
    added.append("ai_score")

if "ai_reason" not in columns:
    conn.execute("ALTER TABLE jobs ADD COLUMN ai_reason TEXT DEFAULT ''")
    added.append("ai_reason")

conn.commit()
conn.close()

if added:
    print(f"Added columns: {', '.join(added)}")
else:
    print("AI columns already exist — no changes needed.")
