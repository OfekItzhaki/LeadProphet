"""Create or restore a consistent SQLite backup using SQLite's backup API."""

import argparse
import sqlite3
from pathlib import Path


def copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
        source_db.backup(destination_db)
        result = destination_db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    copy_database(args.source, args.destination)
    print(f"{args.mode} verified: {args.source} -> {args.destination}")


if __name__ == "__main__":
    main()
