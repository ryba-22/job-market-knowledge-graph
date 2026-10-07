from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


class MigrationRunner:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def migrate(self) -> list[str]:
        applied = []
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            conn.execute(
                """
                create table if not exists schema_migration (
                    version text primary key,
                    checksum text not null,
                    applied_at timestamptz not null default now()
                )
                """
            )
            for path in sorted(MIGRATIONS.glob("*.sql")):
                version = path.name
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                row = conn.execute(
                    "select checksum from schema_migration where version=%s",
                    (version,),
                ).fetchone()
                if row:
                    if row[0] != checksum:
                        raise RuntimeError(
                            f"migration checksum mismatch for {version}: "
                            f"database={row[0]} repository={checksum}"
                        )
                    continue
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        "insert into schema_migration(version, checksum) values (%s,%s)",
                        (version, checksum),
                    )
                applied.append(version)
        return applied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn required")
    for migration in MigrationRunner(args.dsn).migrate():
        print(migration)


if __name__ == "__main__":
    main()
