"""Count [regression] notes per run: regcount.py <run_dir>..."""

import sqlite3
import sys
from pathlib import Path

for root in sys.argv[1:]:
    total = 0
    for db in sorted(Path(root).glob("*/t.db")):
        n = (
            sqlite3.connect(db)
            .execute("SELECT count(*) FROM turns WHERE content LIKE '%[regression]%'")
            .fetchone()[0]
        )
        total += n
        print(f"{db.parent.name}: {n}")
    print(f"{root}: total {total}")
