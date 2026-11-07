# WorkClock weekly email report deployment

## Included changes
- `app.py` is based on the latest uploaded WorkClock app source (`app (2)(2).py`), not the older ZIP's `app.py`.
- Payroll page adds **Send Previous Week's Report Now** and **Send Test Email**.
- Weekly email includes exactly two attachments: `Weekly Payroll Summary.pdf` and `Weekly Attendance Details.xlsx`.
- The report is hours-only: no hourly rates or wage amounts are queried or included.
- Overtime is calculated per employee after 40 hours in the Monday–Sunday reporting week.
- Exceptions include missing punch-in, missing punch-out/open shift, and break started but not ended.
- `weekly_report_worker.py` is a separate one-shot scheduled worker. It avoids repeat scheduled delivery for a period using a table in the same SQLite database.

## Immediate report for November 7, 2026
The previous completed Monday–Sunday period is **October 26 through November 1, 2026**. The app button calculates the previous completed week from the configured Chicago timezone.

## Required Railway setup
1. Deploy the updated web app using the `app.py`, `weekly_report_email.py`, and `requirements.txt` in this package.
2. Keep the existing WorkClock Railway Volume mounted at `/data`. Set `WORKCLOCK_DB_PATH=/data/workclock.db` and `WORKCLOCK_BACKUP_DIR=/data/backups` on both services. Do not attach or use the DHL dashboard volume.
3. Set these variables on the WorkClock web service and scheduled worker:
   - `WORKCLOCK_TIMEZONE=America/Chicago`
   - `WORKCLOCK_REPORT_RECIPIENT=syedegalaspot@gmail.com`
   - `WORKCLOCK_SMTP_HOST` (SMTP server hostname)
   - `WORKCLOCK_SMTP_PORT` (usually 587)
   - `WORKCLOCK_SMTP_USERNAME`
   - `WORKCLOCK_SMTP_PASSWORD` (app password/token, not a personal mailbox password)
   - `WORKCLOCK_SMTP_FROM` (authorized sender address)
4. Add a separate Railway Cron service from the same project/repository, using `railway-weekly-worker.toml` or setting the start command to `python weekly_report_worker.py`. Set its cron schedule to Saturday 08:00 in `America/Chicago` if Railway offers a timezone selector. If the scheduler accepts UTC only, convert the schedule for daylight-saving time; do not use one fixed UTC time year-round.
5. Mount the same WorkClock persistent volume at `/data` on the worker. Never point the worker at the shipping dashboard database or volume.
6. In the WorkClock Payroll page, click **Send Test Email** first. After it succeeds, click **Send Previous Week's Report Now** to send October 26–November 1, 2026.

## Important limitations
- The source package does not contain your live Railway database or SMTP credentials. No email can be sent from this local build until deployed with the live database and SMTP variables.
- The weekly worker's automatic delivery log protects scheduled runs from sending the same period twice. A manual button click intentionally allows a manual resend.
- The app must be reviewed with a backup of the production SQLite database before deploying. No production data has been changed by creating this package.
