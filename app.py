import os
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ADMIN_PIN = "9999"
CHICAGO_TZ = ZoneInfo("America/Chicago")
DB_PATH = os.environ.get("WORKCLOCK_DB_PATH", "/data/workclock.db" if os.path.isdir("/data") else "workclock.db")

LOCAL_NAMES = ["Syed Hassan", "Maria Shuja", "Omer H", "Omar H", "Meryem E", "Maryem E"]
LOCAL_TEAMS = ["local", "local il", "admin", "wh", "warehouse"]
REMOTE_TEAMS = ["remote", "pakistan", "overseas"]
HOURLY_RATES = {
    "Syed Hassan": 18.00,
    "Maria Shuja": 16.00,
    "Meryem E": 13.00,
    "Maryem E": 13.00,
    "Omer H": 14.00,
    "Omar H": 14.00,
}

DEFAULT_EMPLOYEES = [
    ("1", "Syed Hassan", "9999", "Admin", "active"),
    ("3", "Omer H", "1234", "WH", "active"),
    ("5", "Ammar Insaf", "1234", "Remote", "active"),
    ("7", "Khizar Syed", "1234", "Remote", "active"),
    ("8", "Mohammad Sohaib", "1234", "Remote", "active"),
    ("9", "Monu Monu", "1234", "Remote", "active"),
    ("10", "Muhammad Ali", "1234", "Remote", "active"),
    ("11", "Mujtaba Azizi", "1234", "Remote", "active"),
    ("12", "Murtaza Raza", "1234", "Remote", "active"),
    ("13", "Waleed Ahmed", "1234", "Remote", "active"),
    ("14", "Maria Shuja", "1234", "Local", "active"),
    ("15", "Meryem E", "1234", "Local", "active"),
    ("16", "Arham Ahmed", "1342", "Remote", "active"),
]

st.set_page_config(page_title="Egala Spot WorkClock", page_icon="ES", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1280px;padding-top:1rem}.stButton>button{height:62px;font-size:18px;font-weight:900;border-radius:16px}
[data-testid="stSidebar"]{background:#0f172a}[data-testid="stSidebar"] *{color:white!important;font-weight:800}
.header-card{background:white;border-radius:20px;padding:18px 24px;border:1px solid #e5e7eb;box-shadow:0 8px 22px rgba(15,23,42,.06);margin-bottom:16px}
.logo-box{width:66px;height:66px;border-radius:16px;background:linear-gradient(135deg,#2563eb,#0ea5e9);display:flex;justify-content:center;align-items:center;color:white;font-weight:900;font-size:24px}
.time-card{background:linear-gradient(135deg,#1d4ed8,#2563eb 65%,#f59e0b);color:white;border-radius:18px;padding:14px 26px;text-align:center}.time-big{font-size:30px;font-weight:900}.time-small{font-size:12px;font-weight:900;letter-spacing:.12em}.time-date{font-size:12px;font-weight:700}
.status-bar{background:#dbeafe;border:2px solid #60a5fa;border-radius:14px;padding:18px;text-align:center;font-size:22px;font-weight:900;color:#0f172a;margin-top:18px}
.metric-card{background:#f8fafc;border:1px solid #bfdbfe;border-radius:16px;padding:18px;min-height:92px}.metric-label{color:#64748b;text-transform:uppercase;font-size:12px;font-weight:900;letter-spacing:.12em}.metric-value{font-size:24px;font-weight:900;margin-top:8px}
.details-card{margin-top:22px;background:white;border:1px solid #e5e7eb;border-radius:20px;padding:20px}.details-title{font-size:24px;font-weight:900;margin-bottom:14px}
.detail-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:15px}.detail-label{font-size:12px;text-transform:uppercase;color:#64748b;font-weight:900;letter-spacing:.08em}.detail-value{font-size:18px;font-weight:900;margin-top:6px;min-height:24px}
.good{background:#e8f8ef;border:1px solid #bce7c8;color:#106b2f;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px}.warn{background:#fff4e5;border:1px solid #ffd59a;color:#8a4b00;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px}.err{background:#fdecec;border:1px solid #f5b5b5;color:#a10000;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px}
</style>
""", unsafe_allow_html=True)

def chicago_now():
    return datetime.now(CHICAGO_TZ)

def now_text():
    return chicago_now().strftime("%m/%d/%Y %I:%M:%S %p")

def today_text():
    return chicago_now().strftime("%Y-%m-%d")

def display_now():
    return chicago_now().strftime("%I:%M %p").lstrip("0")

def display_date():
    return chicago_now().strftime("%A, %b %d, %Y")

def cid(x):
    return str(x).strip().upper()

@st.cache_resource
def conn():
    parent = Path(DB_PATH).parent
    if str(parent) not in ["", "."]:
        parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""CREATE TABLE IF NOT EXISTS employees(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        pin TEXT NOT NULL DEFAULT '1234',
        team TEXT NOT NULL DEFAULT '',
        active TEXT NOT NULL DEFAULT 'active'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS attendance(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT, name TEXT, team TEXT, work_date TEXT,
        punch_in TEXT, break_start TEXT, break_end TEXT, punch_out TEXT,
        break_hours REAL DEFAULT 0, work_hours REAL DEFAULT 0,
        status TEXT, notes TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, action TEXT, id TEXT, name TEXT, team TEXT,
        status TEXT, message TEXT, notes TEXT
    )""")
    # Add missing columns if an older SQLite file already exists.
    employee_cols = {r[1] for r in c.execute("PRAGMA table_info(employees)").fetchall()}
    for col, sql in {
        "pin": "ALTER TABLE employees ADD COLUMN pin TEXT DEFAULT '1234'",
        "team": "ALTER TABLE employees ADD COLUMN team TEXT DEFAULT ''",
        "active": "ALTER TABLE employees ADD COLUMN active TEXT DEFAULT 'active'",
    }.items():
        if col not in employee_cols:
            c.execute(sql)
    if c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
        c.executemany("INSERT INTO employees(id,name,pin,team,active) VALUES(?,?,?,?,?)", DEFAULT_EMPLOYEES)
    else:
        # Fill blank PINs so current employees can punch.
        for emp_id, name, pin, team, active in DEFAULT_EMPLOYEES:
            exists = c.execute("SELECT id FROM employees WHERE id=?", (emp_id,)).fetchone()
            if not exists:
                c.execute("INSERT INTO employees(id,name,pin,team,active) VALUES(?,?,?,?,?)", (emp_id, name, pin, team, active))
        c.execute("UPDATE employees SET pin='1234' WHERE pin IS NULL OR trim(pin)='' ")
        c.execute("UPDATE employees SET pin='9999' WHERE name='Syed Hassan' AND (pin IS NULL OR trim(pin)='' OR pin='1234')")
    c.commit()
    return c

C = conn()

def read_sql(q, p=()):
    return pd.read_sql_query(q, C, params=p).fillna("")

def exec_sql(q, p=()):
    C.execute(q, p)
    C.commit()

def active_emps():
    return read_sql("SELECT id,name,pin,team,active FROM employees WHERE lower(active) IN ('true','yes','1','active') ORDER BY name")

def find_emp(name, pin):
    r = C.execute("""SELECT * FROM employees
                   WHERE name=? AND pin=? AND lower(active) IN ('true','yes','1','active') LIMIT 1""", (str(name), str(pin).strip())).fetchone()
    return dict(r) if r else None

def safe_dt(x):
    if not str(x or "").strip():
        return None
    v = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(v) else v.to_pydatetime()

def nice_time(x):
    d = safe_dt(x)
    return "-" if d is None else d.strftime("%I:%M %p").lstrip("0")

def calc_hours(pi, bs, be, po):
    pi, bs, be, po = map(safe_dt, [pi, bs, be, po])
    bh = wh = 0.0
    if bs and be:
        bh = round(max((be - bs).total_seconds() / 3600, 0), 2)
    if pi and po:
        gross = max((po - pi).total_seconds() / 3600, 0)
        wh = round(max(gross - bh, 0), 2)
    return bh, wh

def open_shift(emp_id):
    r = C.execute("""SELECT rowid,* FROM attendance
                   WHERE upper(trim(id))=? AND (punch_out IS NULL OR punch_out='')
                   ORDER BY rowid DESC LIMIT 1""", (cid(emp_id),)).fetchone()
    return dict(r) if r else None

def last_shift(emp_id):
    r = C.execute("SELECT rowid,* FROM attendance WHERE upper(trim(id))=? ORDER BY rowid DESC LIMIT 1", (cid(emp_id),)).fetchone()
    return dict(r) if r else None

def today_punches(emp_id):
    return read_sql("""SELECT id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes
                      FROM attendance WHERE upper(trim(id))=? AND work_date=? ORDER BY rowid DESC""", (cid(emp_id), today_text()))

def today_count():
    return C.execute("SELECT COUNT(*) FROM attendance WHERE work_date=?", (today_text(),)).fetchone()[0]

def open_count():
    return C.execute("SELECT COUNT(*) FROM attendance WHERE punch_out IS NULL OR punch_out='' ").fetchone()[0]

def audit(action, emp=None, status="", message="", notes=""):
    row = (now_text(), action, cid(emp.get("id", "")) if emp else "", emp.get("name", "") if emp else "", emp.get("team", "") if emp else "", status, message, notes)
    C.execute("INSERT INTO audit_log(timestamp,action,id,name,team,status,message,notes) VALUES(?,?,?,?,?,?,?,?)", row)
    C.commit()

def msg(kind, text):
    st.markdown(f"<div class='{kind}'>{text}</div>", unsafe_allow_html=True)

def detail(label, value):
    st.markdown(f"<div class='detail-box'><div class='detail-label'>{label}</div><div class='detail-value'>{value}</div></div>", unsafe_allow_html=True)

def office_in(emp, notes):
    if open_shift(emp["id"]):
        audit("Office In Blocked", emp, "Blocked", "Already in office", notes)
        return "err", "Already in office."
    t = now_text()
    C.execute("""INSERT INTO attendance(id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (cid(emp["id"]), emp["name"], emp["team"], today_text(), t, "", "", "", 0, 0, "Working", notes))
    C.commit()
    audit("Office In", emp, "Working", f"Office In saved at {nice_time(t)}", notes)
    return "good", f"Office In saved at {nice_time(t)}"

def start_break(emp, notes):
    cur = open_shift(emp["id"])
    if not cur:
        audit("Start Break Blocked", emp, "Blocked", "Office In first", notes)
        return "warn", "Office In first."
    if cur.get("break_start") and not cur.get("break_end"):
        return "warn", "Already on break."
    if cur.get("break_start") and cur.get("break_end"):
        return "warn", "Break already completed."
    t = now_text()
    exec_sql("UPDATE attendance SET break_start=?,status='On Break' WHERE rowid=?", (t, cur["rowid"]))
    audit("Start Break", emp, "On Break", f"Break started at {nice_time(t)}", notes)
    return "good", f"Break started at {nice_time(t)}"

def end_break(emp, notes):
    cur = open_shift(emp["id"])
    if not cur:
        audit("End Break Blocked", emp, "Blocked", "No active office time", notes)
        return "warn", "No active office time."
    if not cur.get("break_start"):
        return "warn", "No break started."
    if cur.get("break_end"):
        return "warn", "Break already ended."
    t = now_text()
    bh, wh = calc_hours(cur.get("punch_in"), cur.get("break_start"), t, "")
    exec_sql("UPDATE attendance SET break_end=?,break_hours=?,work_hours=?,status='Working' WHERE rowid=?", (t, bh, wh, cur["rowid"]))
    audit("End Break", emp, "Working", f"Break ended at {nice_time(t)}", notes)
    return "good", f"Break ended at {nice_time(t)}"

def office_out(emp, notes):
    cur = open_shift(emp["id"])
    if not cur:
        audit("Office Out Blocked", emp, "Blocked", "No active office time", notes)
        return "warn", "No active office time."
    if cur.get("break_start") and not cur.get("break_end"):
        return "err", "End break first."
    t = now_text()
    bh, wh = calc_hours(cur.get("punch_in"), cur.get("break_start"), cur.get("break_end"), t)
    exec_sql("UPDATE attendance SET punch_out=?,break_hours=?,work_hours=?,status='Completed' WHERE rowid=?", (t, bh, wh, cur["rowid"]))
    audit("Office Out", emp, "Completed", f"Office Out saved at {nice_time(t)}", notes)
    return "good", f"Office Out saved at {nice_time(t)}"

def report_base():
    df = read_sql("SELECT * FROM attendance ORDER BY rowid DESC")
    if df.empty:
        return df
    df["work_date_dt"] = pd.to_datetime(df["work_date"], errors="coerce")
    df["work_num"] = pd.to_numeric(df["work_hours"], errors="coerce").fillna(0)
    df["break_num"] = pd.to_numeric(df["break_hours"], errors="coerce").fillna(0)
    return df

def summarize(df, start, end, group):
    cols = ["id", "name", "team", "total_work_hours", "total_break_hours", "shifts"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    sub = df[(df.work_date_dt >= pd.to_datetime(start)) & (df.work_date_dt <= pd.to_datetime(end))].copy()
    if group == "local":
        sub = sub[sub.name.isin(LOCAL_NAMES) | sub.team.astype(str).str.lower().isin(LOCAL_TEAMS)]
    if group == "remote":
        sub = sub[sub.team.astype(str).str.lower().isin(REMOTE_TEAMS) | (~sub.name.isin(LOCAL_NAMES) & ~sub.team.astype(str).str.lower().isin(LOCAL_TEAMS))]
    if sub.empty:
        return pd.DataFrame(columns=cols)
    s = sub.groupby(["id", "name", "team"], as_index=False).agg(
        total_work_hours=("work_num", "sum"),
        total_break_hours=("break_num", "sum"),
        shifts=("id", "count"),
    )
    s["total_work_hours"] = s.total_work_hours.round(2)
    s["total_break_hours"] = s.total_break_hours.round(2)
    if group == "local":
        s["hourly_rate"] = s.name.map(HOURLY_RATES).fillna(0)
        s["weekly_salary"] = (s.total_work_hours * s.hourly_rate).round(2)
    return s

def excel_bytes(summary, details, title, start, end):
    out = BytesIO()
    try:
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            info = pd.DataFrame({"Report": [title], "Period Start": [str(start)], "Period End": [str(end)], "Created": [now_text()], "DB": [DB_PATH]})
            info.to_excel(w, sheet_name="Report Info", index=False)
            (summary if isinstance(summary, pd.DataFrame) else pd.DataFrame()).to_excel(w, sheet_name="Summary", index=False)
            (details if isinstance(details, pd.DataFrame) else pd.DataFrame()).to_excel(w, sheet_name="Shift Details", index=False)
            for ws in w.book.worksheets:
                ws.sheet_state = "visible"
                ws.freeze_panes = "A2"
    except Exception as e:
        out = BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            pd.DataFrame({"Error": [str(e)], "Created": [now_text()]}).to_excel(w, sheet_name="Export Error", index=False)
    out.seek(0)
    return out.getvalue()

page = st.sidebar.radio("Page", ["Employee Clock", "Admin", "Payroll"])

if page == "Employee Clock":
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown('<div class="header-card"><div style="display:flex;align-items:center;gap:16px"><div class="logo-box">ES</div><div><div style="font-size:32px;font-weight:900;color:#0f172a">Egala Spot</div><div style="color:#2563eb;font-weight:900">Office In • Break • Office Out</div></div></div></div>', unsafe_allow_html=True)
    with h2:
        st.markdown(f"<div class='time-card'><div class='time-small'>CURRENT TIME</div><div class='time-big'>{display_now()}</div><div class='time-date'>{display_date()}</div></div>", unsafe_allow_html=True)

    active = active_emps()
    if active.empty:
        st.error("No active employees found. Go to Admin and add employees.")
        st.stop()
    c1, c2 = st.columns([2, 1])
    selected = c1.selectbox("Employee", active.name.tolist())
    pin = c2.text_input("PIN", type="password")
    notes = st.text_input("Optional Notes", placeholder="Optional - leave blank for normal punch")
    emp = find_emp(selected, pin) if pin else None
    status, last = "Enter PIN", "-"
    if emp:
        cur = open_shift(emp["id"])
        status = "On Break" if cur and cur.get("break_start") and not cur.get("break_end") else ("In Office" if cur else "Not in office")
        last = status if cur else (last_shift(emp["id"]) or {}).get("status", "-")

    def need():
        e = find_emp(selected, pin)
        if not e:
            msg("err", "Wrong PIN. Ask admin to check the employee PIN in Admin > Employees.")
        return e

    cols = st.columns(4)
    actions = [("✅ Office In", office_in), ("☕ Start Break", start_break), ("↩ End Break", end_break), ("🚪 Office Out", office_out)]
    for col, (label, fn) in zip(cols, actions):
        with col:
            if st.button(label, use_container_width=True):
                e = need()
                if e:
                    kind, text = fn(e, notes)
                    msg(kind, text)
                    st.rerun()

    st.markdown(f"<div class='status-bar'>Status: {status}</div>", unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.markdown(f"<div class='metric-card'><div class='metric-label'>Today Punches</div><div class='metric-value'>{today_count()}</div></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-card'><div class='metric-label'>Open Shifts</div><div class='metric-value'>{open_count()}</div></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-card'><div class='metric-label'>Last Action</div><div class='metric-value'>{last}</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='details-card'><div class='details-title'>Employee Shift Details</div>", unsafe_allow_html=True)
    if not pin:
        st.info("Enter PIN to view your shift details.")
    elif not emp:
        st.warning("Correct PIN required to view shift details.")
    else:
        lr = last_shift(emp["id"])
        if lr:
            d = st.columns(4)
            for col, label, key in zip(d, ["Office In", "Break Start", "Break End", "Office Out"], ["punch_in", "break_start", "break_end", "punch_out"]):
                with col:
                    detail(label, nice_time(lr.get(key, "")))
            d = st.columns(4)
            for col, (label, val) in zip(d, [("Work Hours", lr.get("work_hours", "-")), ("Break Hours", lr.get("break_hours", "-")), ("Status", lr.get("status", "-")), ("Team", lr.get("team", "-"))]):
                with col:
                    detail(label, val or "-")
            st.subheader("Your Today's Punches")
            st.dataframe(today_punches(emp["id"]), use_container_width=True, hide_index=True)
        else:
            st.info("No shift record found yet.")
    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Admin":
    st.title("Egala Spot Admin")
    admin = st.sidebar.text_input("Admin PIN", type="password")
    if admin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()
    st.info(f"Storage: SQLite at {DB_PATH}")

    tabs = st.tabs(["Employees", "Attendance", "AuditLog", "Backup/Export"])
    with tabs[0]:
        st.subheader("Employees / PINs")
        st.caption("This page shows PINs so you can fix the new SQLite version. Do not show this screen to employees.")
        emp_df = read_sql("SELECT id,name,pin,team,active FROM employees ORDER BY name")
        st.dataframe(emp_df, use_container_width=True, hide_index=True)
        st.subheader("Update Employee PIN")
        names = emp_df["name"].tolist() if not emp_df.empty else []
        c1, c2 = st.columns([2, 1])
        with c1:
            edit_name = st.selectbox("Employee to update", names) if names else None
        with c2:
            new_pin = st.text_input("New PIN", type="password")
        if st.button("Save PIN", use_container_width=True) and edit_name and new_pin.strip():
            exec_sql("UPDATE employees SET pin=? WHERE name=?", (new_pin.strip(), edit_name))
            st.success(f"PIN updated for {edit_name}")
            st.rerun()
    with tabs[1]:
        df = read_sql("SELECT * FROM attendance ORDER BY rowid DESC")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download Attendance CSV", df.to_csv(index=False).encode(), "attendance.csv", "text/csv")
    with tabs[2]:
        df = read_sql("SELECT * FROM audit_log ORDER BY rowid DESC")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download AuditLog CSV", df.to_csv(index=False).encode(), "audit_log.csv", "text/csv")
    with tabs[3]:
        a = read_sql("SELECT * FROM attendance ORDER BY rowid DESC")
        b = read_sql("SELECT * FROM audit_log ORDER BY rowid DESC")
        st.download_button("Download Full Backup Excel", excel_bytes(a, b, "Full Backup", "", ""), f"egala_spot_backup_{today_text()}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif page == "Payroll":
    st.title("Egala Spot Payroll")
    admin = st.sidebar.text_input("Admin PIN", type="password")
    if admin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()
    base = report_base()
    today = chicago_now().date()
    ws = today - timedelta(days=today.weekday())
    we = ws + timedelta(days=6)
    st.subheader("Weekly Local Report")
    c1, c2 = st.columns(2)
    start = c1.date_input("Local Week Start", value=ws)
    end = c2.date_input("Local Week End", value=we)
    summ = summarize(base, start, end, "local")
    details = base[(base.work_date_dt >= pd.to_datetime(start)) & (base.work_date_dt <= pd.to_datetime(end))].drop(columns=["work_date_dt", "work_num", "break_num"], errors="ignore") if not base.empty else pd.DataFrame()
    st.dataframe(summ, use_container_width=True, hide_index=True)
    st.download_button("Download Weekly Local Payroll Excel", excel_bytes(summ, details, "Weekly Local Payroll", start, end), f"weekly_local_payroll_{start}_to_{end}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    st.divider()
    st.subheader("Monthly Overseas Report")
    ms = today.replace(day=10)
    if today.day < 10:
        ms = (today.replace(day=1) - timedelta(days=1)).replace(day=10)
    me = (ms.replace(day=28) + timedelta(days=4)).replace(day=1).replace(day=9)
    c3, c4 = st.columns(2)
    rs = c3.date_input("Overseas Period Start", value=ms)
    re = c4.date_input("Overseas Period End", value=me)
    rsumm = summarize(base, rs, re, "remote")
    rdetails = base[(base.work_date_dt >= pd.to_datetime(rs)) & (base.work_date_dt <= pd.to_datetime(re))].drop(columns=["work_date_dt", "work_num", "break_num"], errors="ignore") if not base.empty else pd.DataFrame()
    st.dataframe(rsumm, use_container_width=True, hide_index=True)
    st.download_button("Download Monthly Overseas Payroll Excel", excel_bytes(rsumm, rdetails, "Monthly Overseas Payroll", rs, re), f"monthly_overseas_payroll_{rs}_to_{re}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    st.divider()
    st.subheader("All Completed Shift Details")
    st.dataframe(base.drop(columns=["work_date_dt", "work_num", "break_num"], errors="ignore") if not base.empty else pd.DataFrame(), use_container_width=True, hide_index=True)
