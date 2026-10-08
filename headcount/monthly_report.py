import argparse
import sys

from headcount import actors, db, reports


def dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m headcount.monthly_report", description="Cost by team for a month.")
    parser.add_argument("month", help="YYYY-MM")
    args = parser.parse_args(argv)
    conn = db.open_store()
    try:
        report = reports.save_monthly_report(conn, actors.system(conn, "monthly-report"), args.month)
        latest = reports.last_import(conn)
    except db.Refusal as refusal:
        print(f"refused [{refusal.code}]: {refusal}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"Cost for {report['month']}  (headcount {report['headcount']}, total {dollars(report['total_cents'])})")
    for team in report["teams"]:
        print(f"  {team['team']:<20} {team['headcount']:>3}  {dollars(team['cost_cents']):>14}")
    if latest:
        print(f"Last import: {latest['file_name']} at {latest['at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
