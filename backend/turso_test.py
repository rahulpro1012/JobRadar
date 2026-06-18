"""
Turso/libsql diagnostic — run inside the backend container against your test DB:

    docker compose run --rm \
      -e TURSO_DATABASE_URL=libsql://... \
      -e TURSO_AUTH_TOKEN=... \
      backend python turso_test.py

(Or set them in .env and just: docker compose run --rm backend python turso_test.py)

It isolates the write-persistence question: does commit() on a remote libsql
connection survive to a NEW connection? And does embedded-replica + sync()?
Paste the whole output back.
"""
import os
import libsql_experimental as libsql

URL = os.environ.get("TURSO_DATABASE_URL", "")
TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
print("libsql_experimental version:", getattr(libsql, "__version__", "unknown"))
print("URL set:", bool(URL), "| TOKEN set:", bool(TOKEN))
print("-" * 60)

# ---- Test A: remote-only (what the app does now) ----
print("TEST A — remote-only connect, write+commit, read from a NEW connection")
try:
    c1 = libsql.connect(URL, auth_token=TOKEN)
    c1.execute("CREATE TABLE IF NOT EXISTS diag (id INTEGER PRIMARY KEY, v TEXT)")
    c1.execute("DELETE FROM diag")
    c1.execute("INSERT INTO diag (v) VALUES (?)", ("hello",))
    c1.commit()
    # same connection read-back
    same = c1.execute("SELECT COUNT(*) FROM diag").fetchone()
    print("  same-connection count after commit:", same[0] if same else None)
    c1.close()

    c2 = libsql.connect(URL, auth_token=TOKEN)
    new = c2.execute("SELECT COUNT(*) FROM diag").fetchone()
    print("  NEW-connection count after commit:", new[0] if new else None,
          " <-- want 1; if 0, remote commit didn't persist")
    c2.close()
except Exception as e:
    print("  TEST A error:", repr(e))
print("-" * 60)

# ---- Test B: embedded replica (local file + sync_url) + sync() ----
print("TEST B — embedded replica (local file + sync_url), write+commit+sync, read from NEW connection")
try:
    path = "/tmp/diag_replica.db"
    if os.path.exists(path):
        os.remove(path)
    c1 = libsql.connect(path, sync_url=URL, auth_token=TOKEN)
    try:
        c1.sync()  # pull existing remote state
    except Exception as e:
        print("  initial sync() note:", repr(e))
    c1.execute("CREATE TABLE IF NOT EXISTS diag2 (id INTEGER PRIMARY KEY, v TEXT)")
    c1.execute("DELETE FROM diag2")
    c1.execute("INSERT INTO diag2 (v) VALUES (?)", ("hello",))
    c1.commit()
    try:
        c1.sync()  # push local -> remote
    except Exception as e:
        print("  post-write sync() note:", repr(e))
    same = c1.execute("SELECT COUNT(*) FROM diag2").fetchone()
    print("  same-connection count:", same[0] if same else None)
    c1.close()

    c2 = libsql.connect(path, sync_url=URL, auth_token=TOKEN)
    new = c2.execute("SELECT COUNT(*) FROM diag2").fetchone()
    print("  NEW-connection (same local file) count:", new[0] if new else None,
          " <-- want 1")
    c2.close()
except Exception as e:
    print("  TEST B error:", repr(e))
print("-" * 60)
print("Done. Paste this entire output back.")
