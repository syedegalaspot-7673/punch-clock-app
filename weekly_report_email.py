"""WorkClock weekly hours-only email reports. No payroll rates or wages are queried."""
import os
import sqlite3
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

TZ_NAME = os.getenv("WORKCLOCK_TIMEZONE", "America/Chicago")
DEFAULT_RECIPIENT = "syedegalaspot@gmail.com"


def previous_completed_week(reference_date=None):
    local_today = reference_date or datetime.now(ZoneInfo(TZ_NAME)).date()
    this_monday = local_today - timedelta(days=local_today.weekday())
    end = this_monday - timedelta(days=1)
    start = end - timedelta(days=6)
    return start, end


def _parse_dt(value):
    if value is None or str(value).strip() == "":
        return None
    value = str(value).strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def _hours(row):
    pi, bs, be, po = (_parse_dt(row.get(k)) for k in ("punch_in", "break_start", "break_end", "punch_out"))
    if not pi or not po:
        try:
            return round(max(float(row.get("work_hours") or 0), 0), 2)
        except (TypeError, ValueError):
            return 0.0
    if po < pi:
        po += timedelta(hours=12)
        if po < pi:
            po += timedelta(hours=12)
    break_hours = 0.0
    if bs and be:
        if be < bs:
            be += timedelta(hours=12)
            if be < bs:
                be += timedelta(hours=12)
        break_hours = max((be - bs).total_seconds() / 3600, 0)
    return round(max((po - pi).total_seconds() / 3600 - break_hours, 0), 2)


def build_weekly_report(db_path, start, end):
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise FileNotFoundError(f"WorkClock database not found: {db_path}")
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(
            "SELECT id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes "
            "FROM attendance WHERE date(work_date) BETWEEN date(?) AND date(?) ORDER BY name, date(work_date), rowid",
            (str(start), str(end)),
        ).fetchall()]
        employees = [dict(r) for r in con.execute(
            "SELECT id,name,team FROM employees WHERE COALESCE(deleted,0)=0 ORDER BY name"
        ).fetchall()]

    details = pd.DataFrame(rows)
    if details.empty:
        details = pd.DataFrame(columns=["id", "name", "team", "work_date", "punch_in", "break_start", "break_end", "punch_out", "break_hours", "work_hours", "status", "notes"])
    details["Calculated Hours"] = details.apply(lambda r: _hours(r.to_dict()), axis=1) if not details.empty else pd.Series(dtype=float)
    details["Break Hours"] = pd.to_numeric(details.get("break_hours", pd.Series(dtype=float)), errors="coerce").fillna(0).round(2)

    exception_rows = []
    for row in rows:
        problems = []
        if not str(row.get("punch_in") or "").strip():
            problems.append("Missing punch-in")
        if not str(row.get("punch_out") or "").strip():
            problems.append("Missing punch-out / open shift")
        if str(row.get("break_start") or "").strip() and not str(row.get("break_end") or "").strip():
            problems.append("Break started but not ended")
        for problem in problems:
            exception_rows.append({"Employee": row.get("name", ""), "Employee ID": row.get("id", ""), "Date": row.get("work_date", ""), "Issue": problem, "Status": row.get("status", ""), "Notes": row.get("notes", "")})
    exceptions = pd.DataFrame(exception_rows, columns=["Employee", "Employee ID", "Date", "Issue", "Status", "Notes"])

    totals = details.groupby(["id", "name", "team"], dropna=False).agg(
        **{"Total Hours": ("Calculated Hours", "sum"), "Shifts": ("work_date", "count")}
    ).reset_index() if not details.empty else pd.DataFrame(columns=["id", "name", "team", "Total Hours", "Shifts"])
    if not totals.empty:
        totals["Total Hours"] = totals["Total Hours"].round(2)
    else:
        totals = pd.DataFrame(columns=["id", "name", "team", "Total Hours", "Shifts"])
    # Include employees with no shifts in the selected week for a complete review.
    known = set(totals["id"].astype(str)) if not totals.empty else set()
    missing = [{"id": e.get("id"), "name": e.get("name"), "team": e.get("team"), "Total Hours": 0.0, "Shifts": 0} for e in employees if str(e.get("id")) not in known]
    if missing:
        totals = pd.concat([totals, pd.DataFrame(missing)], ignore_index=True)
    if not totals.empty:
        totals = totals.rename(columns={"id": "Employee ID", "name": "Employee", "team": "Team"})
        totals["Regular Hours"] = totals["Total Hours"].clip(upper=40).round(2)
        totals["Overtime Hours"] = (totals["Total Hours"] - 40).clip(lower=0).round(2)
        totals = totals[["Employee ID", "Employee", "Team", "Shifts", "Regular Hours", "Overtime Hours", "Total Hours"]].sort_values("Employee")
    else:
        totals = pd.DataFrame(columns=["Employee ID", "Employee", "Team", "Shifts", "Regular Hours", "Overtime Hours", "Total Hours"])

    # Human-readable detail columns; never include rates, pay, PINs, or database paths.
    detail_columns = [c for c in ["id", "name", "team", "work_date", "punch_in", "break_start", "break_end", "punch_out", "Break Hours", "Calculated Hours", "status", "notes"] if c in details.columns]
    details = details[detail_columns].rename(columns={"id": "Employee ID", "name": "Employee", "team": "Team", "work_date": "Work Date", "punch_in": "Punch In", "break_start": "Break Start", "break_end": "Break End", "punch_out": "Punch Out", "status": "Status", "notes": "Notes"})
    return totals, details, exceptions


def make_excel(totals, details, exceptions, start, end):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        totals.to_excel(writer, sheet_name="Weekly Summary", index=False)
        details.to_excel(writer, sheet_name="Daily Attendance", index=False)
        exceptions.to_excel(writer, sheet_name="Exceptions", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cells in ws.columns:
                width = min(max(max(len(str(c.value or "")) for c in cells) + 2, 12), 42)
                ws.column_dimensions[cells[0].column_letter].width = width
    return output.getvalue()


def make_pdf(totals, exceptions, start, end):
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=0.4*inch, leftMargin=0.4*inch, topMargin=0.45*inch, bottomMargin=0.45*inch)
    styles = getSampleStyleSheet()
    story = [Paragraph("Weekly Payroll Hours Summary", styles["Title"]),
             Paragraph(f"Period: {start:%B %d, %Y} – {end:%B %d, %Y}", styles["Normal"]),
             Paragraph("Hours only. This report is for administrative review and does not approve payroll.", styles["Normal"]), Spacer(1, 12)]
    def add_table(frame):
        data = [list(frame.columns)] + frame.fillna("").astype(str).values.tolist()
        if len(data) == 1:
            data.append(["No records"] + [""] * (len(frame.columns)-1))
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17365D")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#B8C2CC")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F1F5F9")]),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(table)
    story.append(Paragraph("Employee Totals", styles["Heading2"]))
    add_table(totals)
    story.extend([Spacer(1, 12), Paragraph(f"Attendance exceptions: {len(exceptions)}", styles["Heading2"])])
    add_table(exceptions)
    doc.build(story)
    return output.getvalue()


def _smtp_config():
    required = ["WORKCLOCK_SMTP_HOST", "WORKCLOCK_SMTP_USERNAME", "WORKCLOCK_SMTP_PASSWORD", "WORKCLOCK_SMTP_FROM"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Email is not configured. Missing Railway variables: " + ", ".join(missing))
    return {
        "host": os.environ["WORKCLOCK_SMTP_HOST"],
        "port": int(os.getenv("WORKCLOCK_SMTP_PORT", "587")),
        "username": os.environ["WORKCLOCK_SMTP_USERNAME"],
        "password": os.environ["WORKCLOCK_SMTP_PASSWORD"],
        "sender": os.environ["WORKCLOCK_SMTP_FROM"],
        "recipient": os.getenv("WORKCLOCK_REPORT_RECIPIENT", DEFAULT_RECIPIENT),
    }


def send_weekly_report(db_path, start, end, recipient=None):
    totals, details, exceptions = build_weekly_report(db_path, start, end)
    cfg = _smtp_config()
    to_addr = recipient or cfg["recipient"]
    pdf_data = make_pdf(totals, exceptions, start, end)
    xlsx_data = make_excel(totals, details, exceptions, start, end)
    total_hours = round(float(totals["Total Hours"].sum()), 2) if not totals.empty else 0
    regular_hours = round(float(totals["Regular Hours"].sum()), 2) if not totals.empty else 0
    overtime_hours = round(float(totals["Overtime Hours"].sum()), 2) if not totals.empty else 0
    msg = EmailMessage()
    msg["Subject"] = f"WorkClock Weekly Hours Report: {start:%Y-%m-%d} to {end:%Y-%m-%d}"
    msg["From"] = cfg["sender"]
    msg["To"] = to_addr
    msg.set_content(
        f"Weekly WorkClock report\nPeriod: {start:%B %d, %Y} – {end:%B %d, %Y}\n"
        f"Employees in report: {len(totals)}\nRegular hours: {regular_hours:.2f}\n"
        f"Overtime hours: {overtime_hours:.2f}\nTotal hours: {total_hours:.2f}\n"
        f"Attendance exceptions: {len(exceptions)}\n\n"
        "Attached are the PDF weekly summary and Excel daily attendance details. "
        "This report is for admin review only; payroll is not automatically approved."
    )
    msg.add_attachment(pdf_data, maintype="application", subtype="pdf", filename="Weekly Payroll Summary.pdf")
    msg.add_attachment(xlsx_data, maintype="application", subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="Weekly Attendance Details.xlsx")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
        server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.send_message(msg)
    return {"recipient": to_addr, "employees": len(totals), "regular_hours": regular_hours, "overtime_hours": overtime_hours, "total_hours": total_hours, "exceptions": len(exceptions)}


def send_test_email(recipient=None):
    cfg = _smtp_config()
    msg = EmailMessage()
    msg["Subject"] = "WorkClock email configuration test"
    msg["From"] = cfg["sender"]
    msg["To"] = recipient or cfg["recipient"]
    msg.set_content("WorkClock SMTP test succeeded. Weekly hours reports can be sent from this service.")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
        server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.send_message(msg)
    return msg["To"]
