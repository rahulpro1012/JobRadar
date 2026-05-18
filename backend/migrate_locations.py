"""
Run once to add search_locations column to profiles table.
Usage: python migrate_locations.py
Or just delete jobradar.db and restart.
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "jobradar.db")

if not os.path.exists(db_path):
    print("No database found — column will be created on next startup.")
    exit(0)

conn = sqlite3.connect(db_path)
columns = [row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()]

if "search_locations" not in columns:
    conn.execute("ALTER TABLE profiles ADD COLUMN search_locations TEXT DEFAULT '[]'")
    print("Added: search_locations column to profiles")
else:
    print("search_locations column already exists")

# Also ensure ai columns exist on jobs table
job_columns = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
if "ai_score" not in job_columns:
    conn.execute("ALTER TABLE jobs ADD COLUMN ai_score INTEGER DEFAULT NULL")
    print("Added: ai_score column to jobs")
if "ai_reason" not in job_columns:
    conn.execute("ALTER TABLE jobs ADD COLUMN ai_reason TEXT DEFAULT ''")
    print("Added: ai_reason column to jobs")

conn.commit()
conn.close()
print("Migration complete.")
