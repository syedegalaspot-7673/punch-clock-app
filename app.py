
import os
import shutil
import sqlite3
from datetime import datetime, date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

APP_VERSION = "2.1-safe-production-corrected"
ADMIN_PIN = os.environ.get("WORKCLOCK_ADMIN_PIN", "9999")
SUPER_ADMIN_PIN = os.environ.get("WORKCLOCK_SUPER_ADMIN_PIN", "786786")

# Railway should use persistent volume:
# WORKCLOCK_DB_PATH=/data/workclock.db
DB_PATH = os.environ.get("WORKCLOCK_DB_PATH", "/data/workclock.db" if Path("/data").exists() else "workclock.db")
BACKUP_DIR = os.environ.get("WORKCLOCK_BACKUP_DIR", "/data/backups" if Path("/data").exists() else "backups")

LOCAL_NAMES = {"Syed Hassan", "Maria Shuja", "Meryem E", "Maryem E", "Omer H", "Omar H"}
LOCAL_TEAMS = {"local", "local il", "admin", "wh", "warehouse"}
REMOTE_TEAMS = {"remote", "pakistan", "overseas"}

st.set_page_config(page_title="Egala Spot WorkClock", page_icon="ES", layout="wide")

st.markdown("""
<style>
.block-container{max-width:1320px;padding-top:.9rem;padding-bottom:1rem;}
[data-testid="stSidebar"]{background:#0f172a;}
[data-testid="stSidebar"] *{color:white!important;font-weight:800;}
.stButton>button{height:58px;font-size:18px;font-weight:900;border-radius:14px;border:none;box-shadow:0 6px 14px rgba(15,23,42,.10);}
.header-card{background:white;border-radius:20px;padding:18px 24px;border:1px solid #e5e7eb;box-shadow:0 8px 22px rgba(15,23,42,.06);margin-bottom:16px;}
.logo-box{width:66px;height:66px;border-radius:16px;background:linear-gradient(135deg,#2563eb,#0ea5e9);display:flex;justify-content:center;align-items:center;color:white;font-weight:900;font-size:24px;}
.time-card{background:linear-gradient(135deg,#1d4ed8,#2563eb 65%,#f59e0b);color:white;border-radius:18px;padding:14px 26px;text-align:center;box-shadow:0 8px 20px rgba(37,99,235,.25);}
.time-big{font-size:30px;font-weight:900;line-height:1.1;}
.time-small{font-size:12px;font-weight:900;letter-spacing:.12em;}
.time-date{font-size:12px;font-weight:700;}
.status-bar{background:#dbeafe;border:2px solid #60a5fa;border-radius:14px;padding:16px;text-align:center;font-size:24px;font-weight:900;color:#0f172a;margin-top:16px;}
.metric-card{background:#f8fafc;border:1px solid #bfdbfe;border-radius:16px;padding:18px;min-height:92px;}
.metric-label{color:#64748b;text-transform:uppercase;font-size:12px;font-weight:900;letter-spacing:.12em;}
.metric-value{color:#0f172a;font-size:27px;font-weight:900;margin-top:8px;}
.panel{background:white;border:1px solid #e5e7eb;border-radius:18px;padding:18px;margin-top:18px;box-shadow:0 6px 18px rgba(15,23,42,.05);}
.panel-title{font-size:24px;font-weight:900;color:#0f172a;margin-bottom:12px;}
.detail-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:14px;margin-bottom:10px;}
.detail-label{font-size:12px;text-transform:uppercase;color:#64748b;font-weight:900;letter-spacing:.08em;}
.detail-value{font-size:20px;font-weight:900;color:#111827;margin-top:5px;min-height:24px;}
.good{background:#e8f8ef;border:1px solid #bce7c8;color:#106b2f;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
.warn{background:#fff4e5;border:1px solid #ffd59a;color:#8a4b00;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
.err{background:#fdecec;border:1px solid #f5b5b5;color:#a10000;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
.security-note{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:14px;padding:12px 16px;font-weight:900;margin-bottom:12px;}
.profile-card{background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;padding:15px;margin-bottom:10px;box-shadow:0 4px 12px rgba(15,23,42,.05);}
.profile-name{font-size:20px;font-weight:900;color:#0f172a;}
.profile-sub{font-size:14px;color:#64748b;font-weight:800;}
.badge{display:inline-block;background:#e0f2fe;color:#075985;border-radius:999px;padding:4px 10px;font-weight:900;font-size:12px;margin-top:6px;}
</style>
""", unsafe_allow_html=True)

def now():
    return datetime.now()

def now_text():
    return now().strftime("%m/%d/%Y %I:%M:%S %p")

def today_text():
    return now().strftime("%Y-%m-%d")

def display_now():
    return now().strftime("%I:%M %p").lstrip("0")

def display_date():
    return now().strftime("%A, %b %d, %Y")

def cid(x):
    return str(x or "").strip().upper()

def ensure_dirs():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True) if str(Path(DB_PATH).parent) not in ("", ".") else None
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

@st.cache_resource
def get_conn():
    ensure_dirs()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=8000")
    return con

CON = get_conn()

def exec_sql(q, p=()):
    CON.execute(q, p)
    CON.commit()

def read_sql(q, p=()):
    return pd.read_sql_query(q, CON, params=p).fillna("")

def cols(table):
    try:
        return {r[1] for r in CON.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()

def add_col(table, name, ddl):
    if name not in cols(table):
        CON.execute(ddl)
        CON.commit()

def audit(action, emp=None, status="", message="", notes=""):
    try:
        CON.execute("""INSERT INTO audit_log(timestamp,action,id,name,team,status,message,notes)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (now_text(), action,
                     cid(emp.get("id","")) if isinstance(emp, dict) else "",
                     emp.get("name","") if isinstance(emp, dict) else "",
                     emp.get("team","") if isinstance(emp, dict) else "",
                     status, message, notes))
        CON.commit()
    except Exception:
        pass

def migrate():
    # Create only if missing. Never DROP. Never wipe.
    CON.execute("""CREATE TABLE IF NOT EXISTS employees(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        pin TEXT NOT NULL DEFAULT '1234',
        team TEXT NOT NULL DEFAULT '',
        active TEXT NOT NULL DEFAULT 'active'
    )""")
    CON.execute("""CREATE TABLE IF NOT EXISTS attendance(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT,
        name TEXT,
        team TEXT,
        work_date TEXT,
        punch_in TEXT,
        break_start TEXT,
        break_end TEXT,
        punch_out TEXT,
        break_hours REAL DEFAULT 0,
        work_hours REAL DEFAULT 0,
        status TEXT,
        notes TEXT
    )""")
    CON.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        action TEXT,
        id TEXT,
        name TEXT,
        team TEXT,
        status TEXT,
        message TEXT,
        notes TEXT
    )""")
    CON.execute("""CREATE TABLE IF NOT EXISTS system_meta(
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    CON.commit()

    # Safe migrations only add columns.
    add_col("employees", "hourly_rate", "ALTER TABLE employees ADD COLUMN hourly_rate REAL DEFAULT 0")
    add_col("employees", "employee_type", "ALTER TABLE employees ADD COLUMN employee_type TEXT DEFAULT 'remote'")
    add_col("employees", "created_at", "ALTER TABLE employees ADD COLUMN created_at TEXT DEFAULT ''")
    add_col("employees", "updated_at", "ALTER TABLE employees ADD COLUMN updated_at TEXT DEFAULT ''")
    add_col("employees", "deleted", "ALTER TABLE employees ADD COLUMN deleted INTEGER DEFAULT 0")

    add_col("attendance", "manual_entry", "ALTER TABLE attendance ADD COLUMN manual_entry INTEGER DEFAULT 0")
    add_col("attendance", "edited_by", "ALTER TABLE attendance ADD COLUMN edited_by TEXT DEFAULT ''")
    add_col("attendance", "updated_at", "ALTER TABLE attendance ADD COLUMN updated_at TEXT DEFAULT ''")
    add_col("attendance", "locked", "ALTER TABLE attendance ADD COLUMN locked INTEGER DEFAULT 0")

    exec_sql("INSERT OR REPLACE INTO system_meta(key,value) VALUES('app_version',?)", (APP_VERSION,))

def backup_file(reason="backup"):
    ensure_dirs()
    source = Path(DB_PATH)
    if not source.exists() or source.stat().st_size == 0:
        return ""
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(reason))[:35]
    dest = Path(BACKUP_DIR) / f"workclock_{now().strftime('%Y%m%d_%H%M%S')}_{safe}.db"
    shutil.copy2(source, dest)
    audit("DB Backup", None, "OK", str(dest), reason)
    return str(dest)

def daily_backup_once():
    key = f"daily_backup_{today_text()}"
    if st.session_state.get(key):
        return
    try:
        ensure_dirs()
        dest = Path(BACKUP_DIR) / f"workclock_daily_{today_text()}.db"
        if Path(DB_PATH).exists() and not dest.exists():
            shutil.copy2(DB_PATH, dest)
        st.session_state[key] = True
    except Exception:
        st.session_state[key] = True

def seed_only_if_empty():
    count = CON.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if count > 0:
        return
    defaults = [
        ("1","Syed Hassan","9999","Admin","active",18.0,"local"),
        ("14","Maria Shuja","2222","Local","active",16.0,"local"),
        ("15","Meryem E","4444","Local","active",13.0,"local"),
    ]
    for r in defaults:
        CON.execute("""INSERT OR IGNORE INTO employees(id,name,pin,team,active,hourly_rate,employee_type,created_at,updated_at,deleted)
                       VALUES(?,?,?,?,?,?,?,?,?,0)""", (*r, now_text(), now_text()))
    CON.commit()

migrate()
seed_only_if_empty()
daily_backup_once()

def safe_dt(x):
    if not str(x or "").strip():
        return None
    d = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(d) else d.to_pydatetime()

def nice_time(x):
    d = safe_dt(x)
    return "-" if d is None else d.strftime("%I:%M %p").lstrip("0")

def calc_hours(pi, bs, be, po):
    pi, bs, be, po = map(safe_dt, [pi, bs, be, po])
    bh = wh = 0.0
    if pi and po and po < pi:
        po = po + timedelta(hours=12)
        if po < pi:
            po = po + timedelta(hours=12)
    if bs and be and be < bs:
        be = be + timedelta(hours=12)
        if be < bs:
            be = be + timedelta(hours=12)
    if bs and be:
        bh = round(max((be-bs).total_seconds()/3600,0),2)
    if pi and po:
        gross = max((po-pi).total_seconds()/3600,0)
        wh = round(max(gross-bh,0),2)
    return bh, wh

def parse_time(t):
    raw = str(t or "").strip().upper().replace(".","")
    if not raw:
        return None
    for fmt in ["%I:%M %p","%I:%M%p","%I %p","%I%p"]:
        try: return datetime.strptime(raw, fmt).time()
        except Exception: pass
    # 6:00 means PM for manual office-out style entries
    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts)>1 else 0
        if 1 <= hour <= 7:
            hour += 12
        return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
    except Exception:
        return None

def make_dt(day, time_text):
    tm = parse_time(time_text)
    if tm is None:
        raise ValueError(f"Invalid time: {time_text}. Use 9:00 AM, 5:00 PM, or 17:00.")
    return datetime.combine(day, tm).strftime("%m/%d/%Y %I:%M:%S %p")

def active_emps():
    return read_sql("""SELECT id,name,pin,team,active,hourly_rate,employee_type,created_at,updated_at,deleted
                      FROM employees
                      WHERE lower(active) IN ('true','yes','1','active')
                      AND COALESCE(deleted,0)=0
                      ORDER BY name""")

def all_emps():
    return read_sql("""SELECT id,name,pin,team,active,hourly_rate,employee_type,created_at,updated_at,deleted
                      FROM employees
                      ORDER BY COALESCE(deleted,0), name""")

def find_emp(name, pin):
    r = CON.execute("""SELECT * FROM employees
                      WHERE name=? AND pin=? AND lower(active) IN ('true','yes','1','active')
                      AND COALESCE(deleted,0)=0 LIMIT 1""", (str(name), str(pin).strip())).fetchone()
    return dict(r) if r else None

def open_shift(emp_id):
    r = CON.execute("""SELECT rowid,* FROM attendance
                      WHERE upper(trim(id))=? AND (punch_out IS NULL OR punch_out='')
                      ORDER BY rowid DESC LIMIT 1""", (cid(emp_id),)).fetchone()
    return dict(r) if r else None

def last_shift(emp_id):
    r = CON.execute("""SELECT rowid,* FROM attendance WHERE upper(trim(id))=?
                      ORDER BY rowid DESC LIMIT 1""", (cid(emp_id),)).fetchone()
    return dict(r) if r else None

def today_punches(emp_id):
    return read_sql("""SELECT id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes
                      FROM attendance WHERE upper(trim(id))=? AND work_date=?
                      ORDER BY rowid DESC""", (cid(emp_id), today_text()))

def today_count():
    return CON.execute("SELECT COUNT(*) FROM attendance WHERE work_date=?", (today_text(),)).fetchone()[0]

def open_count():
    return CON.execute("SELECT COUNT(*) FROM attendance WHERE punch_out IS NULL OR punch_out=''").fetchone()[0]

def msg(kind, text):
    st.markdown(f"<div class='{kind}'>{text}</div>", unsafe_allow_html=True)

def detail_box(label, value):
    st.markdown(f"<div class='detail-box'><div class='detail-label'>{label}</div><div class='detail-value'>{value}</div></div>", unsafe_allow_html=True)

def office_in(emp, notes):
    if open_shift(emp["id"]):
        audit("Office In Blocked", emp, "Blocked", "Already in office", notes)
        return "err", "Already in office."
    t = now_text()
    exec_sql("""INSERT INTO attendance(id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (cid(emp["id"]), emp["name"], emp["team"], today_text(), t, "", "", "", 0, 0, "Working", notes, t))
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
    exec_sql("UPDATE attendance SET break_start=?,status='On Break',updated_at=? WHERE rowid=?", (t,t,cur["rowid"]))
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
    exec_sql("UPDATE attendance SET break_end=?,break_hours=?,work_hours=?,status='Working',updated_at=? WHERE rowid=?", (t,bh,wh,t,cur["rowid"]))
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
    exec_sql("UPDATE attendance SET punch_out=?,break_hours=?,work_hours=?,status='Completed',updated_at=? WHERE rowid=?", (t,bh,wh,t,cur["rowid"]))
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
    base_cols = ["id","name","team","total_work_hours","total_break_hours","shifts","hourly_rate","total_pay"]
    if df.empty:
        return pd.DataFrame(columns=base_cols)
    sub = df[(df["work_date_dt"] >= pd.to_datetime(start)) & (df["work_date_dt"] <= pd.to_datetime(end))].copy()
    if group == "local":
        sub = sub[sub["name"].isin(LOCAL_NAMES) | sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS)]
    elif group == "remote":
        sub = sub[sub["team"].astype(str).str.lower().isin(REMOTE_TEAMS) | (~sub["name"].isin(LOCAL_NAMES) & ~sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS))]
    if sub.empty:
        return pd.DataFrame(columns=base_cols)
    s = sub.groupby(["id","name","team"], as_index=False).agg(
        total_work_hours=("work_num","sum"),
        total_break_hours=("break_num","sum"),
        shifts=("id","count")
    )
    rates = read_sql("SELECT name,hourly_rate FROM employees")
    rate_map = dict(zip(rates["name"], pd.to_numeric(rates["hourly_rate"], errors="coerce").fillna(0))) if not rates.empty else {}
    s["hourly_rate"] = s["name"].map(rate_map).fillna(0)
    s["total_work_hours"] = s["total_work_hours"].round(2)
    s["total_break_hours"] = s["total_break_hours"].round(2)
    s["total_pay"] = (s["total_work_hours"] * s["hourly_rate"]).round(2)
    return s

def excel_bytes(summary, details, title, start, end):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame({"Report":[title],"Period Start":[str(start)],"Period End":[str(end)],"Created":[now_text()],"DB":[DB_PATH]}).to_excel(w, sheet_name="Report Info", index=False)
        (summary if isinstance(summary,pd.DataFrame) else pd.DataFrame()).to_excel(w, sheet_name="Summary", index=False)
        (details if isinstance(details,pd.DataFrame) else pd.DataFrame()).to_excel(w, sheet_name="Shift Details", index=False)
    out.seek(0)
    return out.getvalue()

def db_bytes():
    CON.commit()
    return Path(DB_PATH).read_bytes() if Path(DB_PATH).exists() else b""

def backup_list():
    ensure_dirs()
    return sorted(Path(BACKUP_DIR).glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)

def save_manual_shift(emp_id, emp_name, emp_team, work_day, punch_in, break_start, break_end, punch_out, notes, rowid=None):
    backup_file("before_manual_payroll_edit")
    bh, wh = calc_hours(punch_in, break_start, break_end, punch_out)
    status = "Completed" if punch_out else ("On Break" if break_start and not break_end else "Working")
    work_day_text = work_day.strftime("%Y-%m-%d") if hasattr(work_day, "strftime") else str(work_day)
    if rowid:
        exec_sql("""UPDATE attendance SET id=?,name=?,team=?,work_date=?,punch_in=?,break_start=?,break_end=?,punch_out=?,
                    break_hours=?,work_hours=?,status=?,notes=?,manual_entry=1,edited_by='admin',updated_at=?
                    WHERE rowid=?""",
                 (cid(emp_id),emp_name,emp_team,work_day_text,punch_in,break_start,break_end,punch_out,bh,wh,status,notes,now_text(),int(rowid)))
        audit("Manual Payroll Edit", {"id":emp_id,"name":emp_name,"team":emp_team}, status, f"Updated row {rowid}. Work hours {wh}, break {bh}", notes)
        return f"Updated shift for {emp_name}. Work hours: {wh}, Break hours: {bh}"
    else:
        exec_sql("""INSERT INTO attendance(id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes,manual_entry,edited_by,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (cid(emp_id),emp_name,emp_team,work_day_text,punch_in,break_start,break_end,punch_out,bh,wh,status,notes,1,"admin",now_text()))
        audit("Manual Payroll Add", {"id":emp_id,"name":emp_name,"team":emp_team}, status, f"Added manual shift. Work hours {wh}, break {bh}", notes)
        return f"Added manual shift for {emp_name}. Work hours: {wh}, Break hours: {bh}"

page = st.sidebar.radio("Page", ["Employee Clock", "Admin", "Payroll", "System"])
admin_pin = st.sidebar.text_input("Admin PIN", type="password", key=f"admin_pin_{page}") if page in ["Admin","Payroll"] else ""

if page == "Employee Clock":
    h1, h2 = st.columns([3,1])
    with h1:
        st.markdown("""<div class="header-card"><div style="display:flex;align-items:center;gap:16px;">
        <div class="logo-box">ES</div><div><div style="font-size:32px;font-weight:900;color:#0f172a;">Egala Spot</div>
        <div style="color:#2563eb;font-weight:900;">Office In • Break • Office Out</div></div></div></div>""", unsafe_allow_html=True)
    with h2:
        st.markdown(f"<div class='time-card'><div class='time-small'>CURRENT TIME</div><div class='time-big'>{display_now()}</div><div class='time-date'>{display_date()}</div></div>", unsafe_allow_html=True)
    emps = active_emps()
    if emps.empty:
        st.error("No active employees found. Go to Admin and add employees.")
        st.stop()
    c1,c2 = st.columns([2,1])
    selected_name = c1.selectbox("Employee", emps["name"].tolist(), key="clock_employee")
    pin = c2.text_input("PIN", type="password", key="clock_pin")
    notes = st.text_input("Optional Notes", placeholder="Optional - leave blank for normal punch", key="clock_notes")
    emp = find_emp(selected_name, pin) if pin else None
    status, last_action = "Enter PIN", "-"
    if emp:
        cur = open_shift(emp["id"])
        if cur:
            status = "On Break" if cur.get("break_start") and not cur.get("break_end") else "In Office"
            last_action = status
        else:
            status = "Not in office"
            lr = last_shift(emp["id"])
            last_action = lr.get("status","-") if lr else "-"

    def need_emp():
        e = find_emp(selected_name, pin)
        if not e:
            msg("err", "Wrong PIN.")
        return e

    cols = st.columns(4)
    for col,label,fn in zip(cols, ["✅ Office In","☕ Start Break","↩ End Break","🚪 Office Out"], [office_in,start_break,end_break,office_out]):
        with col:
            if st.button(label, use_container_width=True):
                e = need_emp()
                if e:
                    kind, text = fn(e, notes)
                    msg(kind, text)
                    st.rerun()

    st.markdown(f"<div class='status-bar'>Status: {status}</div>", unsafe_allow_html=True)
    m1,m2,m3 = st.columns(3)
    with m1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Today Punches</div><div class='metric-value'>{today_count()}</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Open Shifts</div><div class='metric-value'>{open_count()}</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Last Action</div><div class='metric-value'>{last_action}</div></div>", unsafe_allow_html=True)

    st.markdown("<div class='panel'><div class='panel-title'>Employee Shift Details</div>", unsafe_allow_html=True)
    if not pin:
        st.info("Enter PIN to view your shift details.")
    elif not emp:
        st.warning("Correct PIN required to view shift details.")
    else:
        lr = last_shift(emp["id"])
        if lr:
            c = st.columns(4)
            for col,label,key in zip(c, ["Office In","Break Start","Break End","Office Out"], ["punch_in","break_start","break_end","punch_out"]):
                with col: detail_box(label, nice_time(lr.get(key,"")))
            c = st.columns(4)
            for col,(label,val) in zip(c, [("Work Hours",lr.get("work_hours","-")),("Break Hours",lr.get("break_hours","-")),("Status",lr.get("status","-")),("Team",lr.get("team","-"))]):
                with col: detail_box(label, val or "-")
            st.subheader("Today's Punches")
            st.dataframe(today_punches(emp["id"]), use_container_width=True, hide_index=True)
        else:
            st.info("No shift record found yet.")
    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Admin":
    st.title("Egala Spot Admin")
    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()
    st.info(f"Storage: SQLite at {DB_PATH} | Backup folder: {BACKUP_DIR} | Version: {APP_VERSION}")

    tabs = st.tabs(["Dashboard","Employees","Attendance","AuditLog","Backup / Restore"])

    with tabs[0]:
        st.subheader("Live Dashboard")
        open_df = read_sql("""SELECT rowid,id,name,team,work_date,punch_in,break_start,break_end,status,notes
                              FROM attendance WHERE punch_out IS NULL OR punch_out='' ORDER BY rowid DESC""")
        a,b,c = st.columns(3)
        with a: st.markdown(f"<div class='metric-card'><div class='metric-label'>Active Employees</div><div class='metric-value'>{len(active_emps())}</div></div>", unsafe_allow_html=True)
        with b: st.markdown(f"<div class='metric-card'><div class='metric-label'>Currently In</div><div class='metric-value'>{len(open_df)}</div></div>", unsafe_allow_html=True)
        with c: st.markdown(f"<div class='metric-card'><div class='metric-label'>Today Punches</div><div class='metric-value'>{today_count()}</div></div>", unsafe_allow_html=True)
        st.subheader("Currently Clocked In")
        st.dataframe(open_df, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Employee Management")

        top_left, top_mid, top_right = st.columns([2,1,1])
        search = top_left.text_input("Search employee", key="employee_search")
        show_pins = top_mid.checkbox("Show PINs", value=False, key="show_employee_pins")
        reveal_pin = ""
        if show_pins:
            reveal_pin = top_right.text_input("Super Admin PIN", type="password", key="show_pins_super_pin")

        emp_df = all_emps()
        shown = emp_df.copy()
        if search.strip():
            s = search.strip().lower()
            shown = shown[shown.apply(lambda r: s in str(r.get("name","")).lower() or s in str(r.get("team","")).lower() or s in str(r.get("id","")).lower(), axis=1)]

        if show_pins and reveal_pin == SUPER_ADMIN_PIN:
            display_emps = shown.copy()
            audit("Reveal PINs", None, "OK", "Super admin revealed employee PINs", "")
        else:
            display_emps = shown.copy()
            if "pin" in display_emps.columns:
                display_emps["pin"] = "••••"
            if show_pins and reveal_pin:
                st.error("Wrong Super Admin PIN.")

        st.dataframe(display_emps, use_container_width=True, hide_index=True)

        tadd,tedit,tpin,tdis,tdel = st.tabs(["Add Employee","Edit Employee","Reset PIN","Disable/Rehire","Delete"])

        with tadd:
            st.subheader("Add Employee")
            a1,a2,a3 = st.columns(3)
            new_id = a1.text_input("New Employee ID", key="add_id")
            new_name = a2.text_input("Name", key="add_name")
            new_pin = a3.text_input("PIN", type="password", key="add_pin")
            a4,a5,a6 = st.columns(3)
            new_team = a4.text_input("Team", value="Remote", key="add_team")
            new_rate = a5.number_input("Hourly Rate", min_value=0.0, value=0.0, step=0.5, key="add_rate")
            new_type = a6.selectbox("Local / Remote", ["remote","local"], key="add_type")
            if st.button("Add Employee", use_container_width=True, key="btn_add_employee"):
                if not new_id.strip() or not new_name.strip() or not new_pin.strip():
                    st.error("ID, name, and PIN are required.")
                elif CON.execute("SELECT id FROM employees WHERE id=?", (cid(new_id),)).fetchone():
                    st.error("That employee ID already exists.")
                else:
                    backup_file("before_add_employee")
                    exec_sql("""INSERT INTO employees(id,name,pin,team,active,hourly_rate,employee_type,created_at,updated_at,deleted)
                                VALUES(?,?,?,?,?,?,?,?,?,0)""",
                             (cid(new_id), new_name.strip(), new_pin.strip(), new_team.strip(), "active", float(new_rate), new_type, now_text(), now_text()))
                    audit("Add Employee", {"id":cid(new_id),"name":new_name,"team":new_team}, "active", "Employee added", "")
                    st.success(f"Added {new_name}")
                    st.rerun()

        with tedit:
            st.subheader("Edit Employee")
            emp_edit = all_emps()
            if emp_edit.empty:
                st.info("No employees.")
            else:
                selected = st.selectbox("Employee", emp_edit["name"].tolist(), key="edit_employee_select")
                row = emp_edit[emp_edit["name"] == selected].iloc[0].to_dict()
                e1,e2,e3 = st.columns(3)
                edit_name = e1.text_input("Name", value=row.get("name",""), key=f"edit_name_{row.get('id')}")
                edit_team = e2.text_input("Team", value=row.get("team",""), key=f"edit_team_{row.get('id')}")
                edit_rate = e3.number_input("Hourly Rate", min_value=0.0, value=float(row.get("hourly_rate") or 0), step=0.5, key=f"edit_rate_{row.get('id')}")
                e4,e5 = st.columns(2)
                edit_type = e4.selectbox("Local / Remote", ["remote","local"], index=1 if str(row.get("employee_type","remote")).lower()=="local" else 0, key=f"edit_type_{row.get('id')}")
                edit_status = e5.selectbox("Status", ["active","inactive"], index=0 if str(row.get("active","active")).lower()=="active" else 1, key=f"edit_status_{row.get('id')}")
                if st.button("Save Employee Changes", use_container_width=True, key=f"btn_save_emp_{row.get('id')}"):
                    backup_file("before_edit_employee")
                    exec_sql("""UPDATE employees SET name=?,team=?,hourly_rate=?,employee_type=?,active=?,updated_at=? WHERE id=?""",
                             (edit_name.strip(), edit_team.strip(), float(edit_rate), edit_type, edit_status, now_text(), row["id"]))
                    audit("Edit Employee", {"id":row["id"],"name":edit_name,"team":edit_team}, edit_status, "Employee updated", "")
                    st.success("Employee updated.")
                    st.rerun()

        with tpin:
            st.subheader("Reset PIN")
            emp_pin = all_emps()
            if not emp_pin.empty:
                selected = st.selectbox("Employee", emp_pin["name"].tolist(), key="pin_employee_select")
                row = emp_pin[emp_pin["name"] == selected].iloc[0].to_dict()
                new_pin = st.text_input("New PIN", type="password", key=f"reset_pin_{row.get('id')}")
                if st.button("Reset PIN", use_container_width=True, key=f"btn_reset_pin_{row.get('id')}"):
                    if not new_pin.strip():
                        st.error("PIN cannot be empty.")
                    else:
                        backup_file("before_reset_pin")
                        exec_sql("UPDATE employees SET pin=?,updated_at=? WHERE id=?", (new_pin.strip(), now_text(), row["id"]))
                        audit("Reset PIN", {"id":row["id"],"name":row["name"],"team":row["team"]}, "OK", "PIN reset", "")
                        st.success("PIN reset.")
                        st.rerun()

        with tdis:
            st.subheader("Disable / Rehire")
            emp_dis = all_emps()
            if not emp_dis.empty:
                selected = st.selectbox("Employee", emp_dis["name"].tolist(), key="disable_employee_select")
                row = emp_dis[emp_dis["name"] == selected].iloc[0].to_dict()
                c1,c2 = st.columns(2)
                if c1.button("Disable Employee", use_container_width=True, key=f"disable_{row.get('id')}"):
                    backup_file("before_disable_employee")
                    exec_sql("UPDATE employees SET active='inactive',updated_at=? WHERE id=?", (now_text(), row["id"]))
                    audit("Disable Employee", row, "inactive", "Employee disabled", "")
                    st.success("Employee disabled.")
                    st.rerun()
                if c2.button("Rehire / Reactivate", use_container_width=True, key=f"rehire_{row.get('id')}"):
                    backup_file("before_rehire_employee")
                    exec_sql("UPDATE employees SET active='active',deleted=0,updated_at=? WHERE id=?", (now_text(), row["id"]))
                    audit("Rehire Employee", row, "active", "Employee reactivated", "")
                    st.success("Employee reactivated.")
                    st.rerun()

        with tdel:
            st.subheader("Delete Employee")
            st.warning("This soft-deletes employee from active screens but keeps attendance/payroll history.")
            super_pin = st.text_input("Super Admin PIN", type="password", key="delete_super_pin")
            emp_del = all_emps()
            if not emp_del.empty:
                selected = st.selectbox("Employee", emp_del["name"].tolist(), key="delete_employee_select")
                row = emp_del[emp_del["name"] == selected].iloc[0].to_dict()
                if st.button("Delete Employee", use_container_width=True, key=f"delete_{row.get('id')}"):
                    if super_pin != SUPER_ADMIN_PIN:
                        st.error("Wrong Super Admin PIN.")
                    else:
                        backup_file("before_delete_employee")
                        exec_sql("UPDATE employees SET active='inactive',deleted=1,updated_at=? WHERE id=?", (now_text(), row["id"]))
                        audit("Delete Employee", row, "deleted", "Soft deleted employee", "")
                        st.success("Employee deleted from active screens. History kept.")
                        st.rerun()

    with tabs[2]:
        st.subheader("Attendance")
        df = read_sql("SELECT * FROM attendance ORDER BY rowid DESC")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download Attendance CSV", df.to_csv(index=False).encode("utf-8"), "attendance.csv", "text/csv")

    with tabs[3]:
        st.subheader("AuditLog")
        df = read_sql("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT 1000")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download AuditLog CSV", df.to_csv(index=False).encode("utf-8"), "audit_log.csv", "text/csv")

    with tabs[4]:
        st.subheader("Backup / Restore")
        st.write(f"DB Path: `{DB_PATH}`")
        st.write(f"Backup Folder: `{BACKUP_DIR}`")
        c1,c2 = st.columns(2)
        if c1.button("Create DB Backup Now", use_container_width=True, key="create_backup"):
            p = backup_file("manual_backup")
            st.success(f"Backup created: {p}" if p else "No DB found.")
        c2.download_button("Download Current Database", db_bytes(), f"workclock_backup_{today_text()}.db", "application/octet-stream", use_container_width=True)

        att = read_sql("SELECT * FROM attendance ORDER BY rowid DESC")
        aud = read_sql("SELECT * FROM audit_log ORDER BY rowid DESC")
        st.download_button("Emergency Full Excel Export", excel_bytes(att, aud, "Emergency Full Backup", "", ""), f"egala_spot_emergency_backup_{today_text()}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        st.subheader("Backup History")
        files = backup_list()
        if files:
            hist = pd.DataFrame([{"file":f.name,"size_kb":round(f.stat().st_size/1024,2),"modified":datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %I:%M %p")} for f in files])
            st.dataframe(hist, use_container_width=True, hide_index=True)
            st.warning("Restore replaces current DB. A backup is made first. Restart app after restore.")
            choice = st.selectbox("Choose backup to restore", [f.name for f in files], key="restore_choice")
            restore_pin = st.text_input("Super Admin PIN for restore", type="password", key="restore_pin")
            if st.button("Restore Selected Backup", use_container_width=True, key="restore_backup"):
                if restore_pin != SUPER_ADMIN_PIN:
                    st.error("Wrong Super Admin PIN.")
                else:
                    backup_file("before_restore")
                    shutil.copy2(Path(BACKUP_DIR)/choice, DB_PATH)
                    st.success("Backup restored. Restart app now.")
        else:
            st.info("No backups yet.")

elif page == "Payroll":
    st.title("Egala Spot Payroll")
    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()
    base = report_base()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    st.subheader("Weekly Local Report")
    c1,c2 = st.columns(2)
    local_start = c1.date_input("Local Week Start", value=week_start, key="local_start")
    local_end = c2.date_input("Local Week End", value=week_end, key="local_end")
    local_summary = summarize(base, local_start, local_end, "local")
    local_details = base[(base["work_date_dt"] >= pd.to_datetime(local_start)) & (base["work_date_dt"] <= pd.to_datetime(local_end))].drop(columns=["work_date_dt","work_num","break_num"], errors="ignore") if not base.empty else pd.DataFrame()
    st.dataframe(local_summary, use_container_width=True, hide_index=True)
    st.download_button("Download Weekly Local Payroll Excel", excel_bytes(local_summary, local_details, "Weekly Local Payroll", local_start, local_end), f"weekly_local_payroll_{local_start}_to_{local_end}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.divider()
    st.subheader("Monthly Overseas Report")
    month_start = today.replace(day=10)
    if today.day < 10:
        month_start = (today.replace(day=1)-timedelta(days=1)).replace(day=10)
    month_end = (month_start.replace(day=28)+timedelta(days=4)).replace(day=1).replace(day=9)
    c3,c4 = st.columns(2)
    remote_start = c3.date_input("Overseas Period Start", value=month_start, key="remote_start")
    remote_end = c4.date_input("Overseas Period End", value=month_end, key="remote_end")
    remote_summary = summarize(base, remote_start, remote_end, "remote")
    remote_details = base[(base["work_date_dt"] >= pd.to_datetime(remote_start)) & (base["work_date_dt"] <= pd.to_datetime(remote_end))].drop(columns=["work_date_dt","work_num","break_num"], errors="ignore") if not base.empty else pd.DataFrame()
    st.dataframe(remote_summary, use_container_width=True, hide_index=True)
    st.download_button("Download Monthly Overseas Payroll Excel", excel_bytes(remote_summary, remote_details, "Monthly Overseas Payroll", remote_start, remote_end), f"monthly_overseas_payroll_{remote_start}_to_{remote_end}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.divider()
    st.subheader("Manual Payroll Edit")
    st.caption("Manual saves create a database backup and AuditLog record.")
    if st.button("Repair Manual Hours / Refresh Payroll Totals", use_container_width=True, key="repair_hours"):
        rows = read_sql("SELECT rowid,punch_in,break_start,break_end,punch_out FROM attendance")
        for _, r in rows.iterrows():
            bh, wh = calc_hours(r.get("punch_in",""), r.get("break_start",""), r.get("break_end",""), r.get("punch_out",""))
            exec_sql("UPDATE attendance SET break_hours=?,work_hours=?,updated_at=? WHERE rowid=?", (bh,wh,now_text(),int(r["rowid"])))
        audit("Repair Manual Hours", None, "Completed", f"Recalculated {len(rows)} rows", "")
        st.success(f"Recalculated {len(rows)} rows.")
        st.rerun()

    mode = st.radio("Manual action", ["Add Missing Shift","Edit Existing Shift","Delete Shift"], horizontal=True, key="manual_mode")
    emp_df = read_sql("SELECT id,name,team FROM employees WHERE COALESCE(deleted,0)=0 ORDER BY name")

    if mode == "Add Missing Shift":
        if emp_df.empty:
            st.warning("No employees.")
        else:
            selected = st.selectbox("Employee / Owner", emp_df["name"].tolist(), key="manual_add_emp")
            erow = emp_df[emp_df["name"] == selected].iloc[0].to_dict()
            c1,c2,c3 = st.columns(3)
            work_day = c1.date_input("Work Date", value=today, key="manual_add_date")
            t_in = c2.text_input("Office In Time", value="9:00 AM", key="manual_add_in")
            t_out = c3.text_input("Office Out Time", value="5:00 PM", key="manual_add_out")
            c4,c5 = st.columns(2)
            has_break = c4.checkbox("Include Break", value=False, key="manual_add_break")
            note = c5.text_input("Reason / Notes", value="Manual payroll correction", key="manual_add_note")
            bstart = bend = ""
            if has_break:
                c6,c7 = st.columns(2)
                bstart_text = c6.text_input("Break Start Time", value="12:00 PM", key="manual_add_bstart")
                bend_text = c7.text_input("Break End Time", value="12:30 PM", key="manual_add_bend")
            if st.button("Save Manual Missing Shift", use_container_width=True, key="save_manual_add"):
                try:
                    pi = make_dt(work_day, t_in)
                    po = make_dt(work_day, t_out)
                    if has_break:
                        bstart = make_dt(work_day, bstart_text)
                        bend = make_dt(work_day, bend_text)
                    st.success(save_manual_shift(erow["id"], erow["name"], erow["team"], work_day, pi, bstart, bend, po, note))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    elif mode == "Edit Existing Shift":
        existing = read_sql("""SELECT rowid,id,name,team,work_date,punch_in,break_start,break_end,punch_out,break_hours,work_hours,status,notes
                               FROM attendance ORDER BY rowid DESC LIMIT 500""")
        if existing.empty:
            st.info("No shifts to edit.")
        else:
            existing["label"] = existing.apply(lambda r: f"Row {r['rowid']} | {r['name']} | {r['work_date']} | {r['status']} | {r['work_hours']} hrs", axis=1)
            label = st.selectbox("Select shift", existing["label"].tolist(), key="manual_edit_select")
            row = existing[existing["label"] == label].iloc[0].to_dict()
            names = emp_df["name"].tolist()
            idx = names.index(row["name"]) if row["name"] in names else 0
            selected = st.selectbox("Employee / Owner", names, index=idx, key="manual_edit_emp")
            erow = emp_df[emp_df["name"] == selected].iloc[0].to_dict()
            d = pd.to_datetime(row.get("work_date",""), errors="coerce")
            if pd.isna(d): d = pd.Timestamp(today)
            c1,c2,c3 = st.columns(3)
            work_day = c1.date_input("Work Date", value=d.date(), key="manual_edit_date")
            t_in = c2.text_input("Office In Time", value=nice_time(row.get("punch_in","")) if nice_time(row.get("punch_in",""))!="-" else "9:00 AM", key="manual_edit_in")
            t_out = c3.text_input("Office Out Time", value=nice_time(row.get("punch_out","")) if nice_time(row.get("punch_out",""))!="-" else "5:00 PM", key="manual_edit_out")
            c4,c5 = st.columns(2)
            has_break = c4.checkbox("Include Break", value=bool(str(row.get("break_start","")).strip()), key="manual_edit_break")
            note = c5.text_input("Reason / Notes", value=str(row.get("notes","") or "Manual payroll correction"), key="manual_edit_note")
            bstart = bend = ""
            if has_break:
                c6,c7 = st.columns(2)
                bstart_text = c6.text_input("Break Start Time", value=nice_time(row.get("break_start","")) if nice_time(row.get("break_start",""))!="-" else "12:00 PM", key="manual_edit_bstart")
                bend_text = c7.text_input("Break End Time", value=nice_time(row.get("break_end","")) if nice_time(row.get("break_end",""))!="-" else "12:30 PM", key="manual_edit_bend")
            if st.button("Save Edited Shift", use_container_width=True, key="save_manual_edit"):
                try:
                    pi = make_dt(work_day, t_in)
                    po = make_dt(work_day, t_out)
                    if has_break:
                        bstart = make_dt(work_day, bstart_text)
                        bend = make_dt(work_day, bend_text)
                    st.success(save_manual_shift(erow["id"], erow["name"], erow["team"], work_day, pi, bstart, bend, po, note, rowid=row["rowid"]))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    else:
        st.warning("Delete shift only for wrong duplicate records. Backup and AuditLog are created.")
        existing = read_sql("SELECT rowid,id,name,team,work_date,punch_in,punch_out,work_hours,status FROM attendance ORDER BY rowid DESC LIMIT 500")
        if existing.empty:
            st.info("No shifts.")
        else:
            existing["label"] = existing.apply(lambda r: f"Row {r['rowid']} | {r['name']} | {r['work_date']} | {r['status']} | {r['work_hours']} hrs", axis=1)
            label = st.selectbox("Select shift to delete", existing["label"].tolist(), key="manual_delete_select")
            row = existing[existing["label"] == label].iloc[0].to_dict()
            confirm = st.text_input("Type DELETE to confirm", key="delete_shift_confirm")
            if st.button("Delete Selected Shift", use_container_width=True, key="delete_shift_btn"):
                if confirm != "DELETE":
                    st.error("Type DELETE first.")
                else:
                    backup_file("before_delete_shift")
                    exec_sql("DELETE FROM attendance WHERE rowid=?", (int(row["rowid"]),))
                    audit("Delete Shift", row, "Deleted", f"Deleted attendance row {row['rowid']}", "")
                    st.success("Shift deleted.")
                    st.rerun()

    st.divider()
    st.subheader("All Completed Shift Details")
    st.dataframe(base.drop(columns=["work_date_dt","work_num","break_num"], errors="ignore") if not base.empty else pd.DataFrame(), use_container_width=True, hide_index=True)

elif page == "System":
    st.title("System Stability")
    st.write(f"Version: `{APP_VERSION}`")
    st.write(f"Database Path: `{DB_PATH}`")
    st.write(f"Backup Folder: `{BACKUP_DIR}`")
    st.write(f"Database Exists: `{Path(DB_PATH).exists()}`")
    st.write(f"Database Size KB: `{round(Path(DB_PATH).stat().st_size/1024,2) if Path(DB_PATH).exists() else 0}`")
    st.warning("For Railway production, use persistent volume and set WORKCLOCK_DB_PATH=/data/workclock.db.")
