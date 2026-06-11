import sys

sys.path.insert(0, ".")
from services.novel_db.connection import with_db

with with_db() as conn:
    rows = conn.execute(
        "SELECT id, state, mode, target_id, started_at FROM rebuild_jobs ORDER BY id DESC LIMIT 5"
    ).fetchall()
    print("=== rebuild_jobs (最新5件) ===")
    for r in rows:
        print(r)
    wal = conn.execute("PRAGMA journal_mode").fetchone()
    print("journal_mode:", wal)
