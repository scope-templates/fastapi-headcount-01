"""Usage: python -m headcount.import <file.csv> --by <person id> [--force --reason "..."]

Prints one summary line, or "refused [code]: ..." and exits 1."""

import argparse
import sys
from pathlib import Path

from headcount import actors, db, importer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m headcount.import", description="Load the monthly people and pay file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--by", required=True, help="person id of whoever runs the import (finance role)")
    parser.add_argument("--force", action="store_true", help="accept a headcount swing of more than a fifth")
    parser.add_argument("--reason", help="why a forced import is right")
    args = parser.parse_args(argv)
    if not args.file.is_file():
        print(f"refused [no_such_file]: no file at {args.file}", file=sys.stderr)
        return 1
    conn = db.open_store()
    try:
        result = importer.run_import(conn, actors.person(conn, args.by), args.file, args.force, args.reason)
    except db.Refusal as refusal:
        print(f"refused [{refusal.code}]: {refusal}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    delta = "first import" if result["headcount_delta"] is None else f"{result['headcount_delta']:+d}"
    print(
        f"import {result['import_id']}: {result['file_name']}, {result['row_count']} rows, headcount"
        f" {result['headcount']} ({delta}); {result['people_added']} people added, {result['people_updated']}"
        f" updated, {result['pay_rows_added']} pay rows added"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
