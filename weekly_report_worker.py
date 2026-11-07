"""One-shot Railway Cron worker: run every Saturday at 08:00 America/Chicago."""
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from weekly_report_email import previous_completed_week, send_weekly_report

DB_PATH = os.getenv("WORKCLOCK_DB_PATH", "/data/workclock.db")
TZ_NAME = os.getenv("WORKCLOCK_TIMEZONE", "America/Chicago")


def main():
    start, end = previous_completed_week(datetime.now(ZoneInfo(TZ_NAME)).date())
    with sqlite3.connect(DB_PATH) as con:
        con.execute("CREATE TABLE IF NOT EXISTS weekly_report_delivery (period_start TEXT NOT NULL, period_end TEXT NOT NULL, sent_at TEXT NOT NULL, recipient TEXT NOT NULL, PRIMARY KEY(period_start, period_end))")
        existing = con.execute("SELECT sent_at FROM weekly_report_delivery WHERE period_start=? AND period_end=?", (str(start), str(end))).fetchone()
        if existing:
            print(f"Report already sent for {start} to {end} at {existing[0]}; skipping.")
            return
    result = send_weekly_report(DB_PATH, start, end)
    sent_at = datetime.now(ZoneInfo(TZ_NAME)).isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("CREATE TABLE IF NOT EXISTS weekly_report_delivery (period_start TEXT NOT NULL, period_end TEXT NOT NULL, sent_at TEXT NOT NULL, recipient TEXT NOT NULL, PRIMARY KEY(period_start, period_end))")
        con.execute("INSERT OR IGNORE INTO weekly_report_delivery(period_start,period_end,sent_at,recipient) VALUES(?,?,?,?)", (str(start), str(end), sent_at, result["recipient"]))
        con.commit()
    print(f"Sent report for {start} to {end}: {result}")


if __name__ == "__main__":
    main()
