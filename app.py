
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from io import BytesIO
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

SHEET_ID = "1PIYrwnqIwSNcCdAfNLniGuhCYoIe3YUbpQzXTYxCovw"
ADMIN_PIN = "9999"

EMP_HEADERS = ["id", "name", "pin", "team", "active"]
LOG_HEADERS = ["id","name","team","work_date","punch_in","break_start","break_end","punch_out","break_hours","work_hours","status","notes"]
AUDIT_HEADERS = ["timestamp","action","id","name","team","status","message","notes"]
BACKUP_HEADERS = ["backup_time","backup_reason"] + LOG_HEADERS
PAYROLL_ARCHIVE_HEADERS = [
    "snapshot_time","report_type","period_start","period_end",
    "id","name","team","total_work_hours","total_break_hours","shifts","notes"
]

LOCAL_NAMES = ["Syed Hassan", "Maria Shuja", "Omer H", "Meryem E"]
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

st.set_page_config(page_title="Egala Spot WorkClock", page_icon="ES", layout="wide")

st.markdown("""
<style>
.block-container{max-width:1280px;padding-top:1.1rem;padding-bottom:1rem;}
[data-testid="stSidebar"]{background:#0f172a;}
[data-testid="stSidebar"] *{color:white!important;font-weight:700;}
.main-shell{background:linear-gradient(135deg,#f8fbff 0%,#fff 52%,#fff7ed 100%);border-radius:22px;padding:20px 26px 24px;border:1px solid #e5e7eb;box-shadow:0 8px 28px rgba(15,23,42,.07);}
.header-card{background:white;border-radius:20px;padding:18px 24px;border:1px solid #e5e7eb;box-shadow:0 8px 22px rgba(15,23,42,.06);margin-bottom:16px;}
.logo-box{width:66px;height:66px;border-radius:16px;background:linear-gradient(135deg,#2563eb,#0ea5e9);display:flex;justify-content:center;align-items:center;color:white;font-weight:900;font-size:24px;}
.time-card{background:linear-gradient(135deg,#1d4ed8,#2563eb 65%,#f59e0b);color:white;border-radius:18px;padding:14px 26px;text-align:center;box-shadow:0 8px 20px rgba(37,99,235,.25);}
.time-big{font-size:30px;font-weight:900;line-height:1.1;}
.time-small{font-size:12px;font-weight:900;letter-spacing:.12em;}
.time-date{font-size:12px;font-weight:700;}
.form-card{background:white;border-radius:18px;padding:18px 20px 20px;border:1px solid #e5e7eb;}
.stButton>button{height:62px;font-size:18px;font-weight:900;border-radius:16px;border:none;box-shadow:0 10px 20px rgba(15,23,42,.10);}
.status-bar{background:#dbeafe;border:2px solid #60a5fa;border-radius:14px;padding:18px;text-align:center;font-size:22px;font-weight:900;color:#0f172a;margin-top:18px;}
.metric-card{background:#f8fafc;border:1px solid #bfdbfe;border-radius:16px;padding:18px;min-height:92px;}
.metric-label{color:#64748b;text-transform:uppercase;font-size:12px;font-weight:900;letter-spacing:.12em;}
.metric-value{color:#0f172a;font-size:24px;font-weight:900;margin-top:8px;}
.details-card{margin-top:22px;background:white;border:1px solid #e5e7eb;border-radius:20px;padding:20px;box-shadow:0 8px 22px rgba(15,23,42,.05);}
.details-title{font-size:24px;font-weight:900;color:#0f172a;margin-bottom:14px;}
.detail-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:15px;}
.detail-label{font-size:12px;text-transform:uppercase;color:#64748b;font-weight:900;letter-spacing:.08em;}
.detail-value{font-size:18px;font-weight:900;color:#111827;margin-top:6px;min-height:24px;}
.good{background:#e8f8ef;border:1px solid #bce7c8;color:#106b2f;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
.warn{background:#fff4e5;border:1px solid #ffd59a;color:#8a4b00;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
.err{background:#fdecec;border:1px solid #f5b5b5;color:#a10000;border-radius:12px;padding:14px 18px;font-size:17px;font-weight:800;margin-top:14px;}
</style>
""", unsafe_allow_html=True)

CHICAGO_TZ = ZoneInfo("America/Chicago")

def chicago_now():
    return datetime.now(CHICAGO_TZ)

def chicago_today():
    return chicago_now().date()

def now_text(): return chicago_now().strftime("%Y-%m-%d %H:%M:%S")
def display_now(): return chicago_now().strftime("%I:%M %p").lstrip("0")
def display_date(): return chicago_now().strftime("%A, %b %d, %Y")
def cid(x): return str(x).strip().upper()

def get_secret():
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            if "private_key" in info:
                info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
            return info
    except Exception:
        return None
    return None

@st.cache_resource
def connect_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if Path("credentials.json").exists():
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        return gspread.authorize(creds).open_by_key(SHEET_ID)
    info = get_secret()
    if info:
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds).open_by_key(SHEET_ID)
    st.error("Google credentials missing. Put credentials.json in the same folder as app.py.")
    st.stop()

def get_ws(sheet, name, headers):
    try:
        ws = sheet.worksheet(name)
    except WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=5000, cols=max(len(headers), 20))
        ws.append_row(headers)
        return ws
    vals = ws.get_all_values()
    if not vals:
        ws.append_row(headers)
    elif vals[0] != headers:
        st.warning(f"{name} headers do not match expected format. Existing data was NOT erased.")
    return ws

def read_ws(ws, headers, keep_row_number=False):
    vals = ws.get_all_values()
    if len(vals) <= 1:
        df = pd.DataFrame(columns=headers, dtype=str)
        if keep_row_number: df["_row"] = []
        return df
    rows, row_numbers = [], []
    for sheet_row_num, r in enumerate(vals[1:], start=2):
        r = (r + [""] * len(headers))[:len(headers)]
        if r == headers or str(r[0]).strip().lower() in ["", "id"]:
            continue
        rows.append(r); row_numbers.append(sheet_row_num)
    df = pd.DataFrame(rows, columns=headers).fillna("")
    for c in headers: df[c] = df[c].astype(str)
    if keep_row_number: df["_row"] = row_numbers
    return df

def safe_dt(x):
    x = str(x).strip()
    if x == "" or x.lower() in ["none", "nan"]: return None
    v = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(v) else v

def nice_time(x):
    dt = safe_dt(x)
    return "-" if dt is None else dt.strftime("%I:%M %p").lstrip("0")

def calc_logs(df):
    if df.empty: return df
    df = df.copy()
    for c in LOG_HEADERS:
        if c not in df.columns: df[c] = ""
        df[c] = df[c].fillna("").astype(str)
    for i, r in df.iterrows():
        pi, po = safe_dt(r.get("punch_in","")), safe_dt(r.get("punch_out",""))
        bs, be = safe_dt(r.get("break_start","")), safe_dt(r.get("break_end",""))
        bh, wh = "", ""
        if bs is not None and be is not None:
            bh = str(round(max((be-bs).total_seconds()/3600,0),2))
        if pi is not None and po is not None:
            gross = max((po-pi).total_seconds()/3600,0)
            wh = str(round(max(gross-(float(bh) if bh else 0),0),2))
        df.at[i,"break_hours"] = bh
        df.at[i,"work_hours"] = wh
    return df.astype(str)

def active_employees(df):
    if df.empty: return df
    e = df.copy()
    e["active"] = e["active"].astype(str).str.lower().str.strip()
    return e[e["active"].isin(["true","yes","1","active"])]

def find_emp_by_name_pin(emp, name, pin):
    e = active_employees(emp)
    if e.empty: return None
    m = e[(e["name"].astype(str)==str(name)) & (e["pin"].astype(str).str.strip()==str(pin).strip())]
    return None if m.empty else m.iloc[0]

def open_shift(logs, emp_id):
    if logs.empty: return logs
    return logs[(logs["id"].astype(str).str.strip().str.upper()==cid(emp_id)) & (logs["punch_out"].astype(str).str.strip()=="")]

def employee_rows(logs, emp_id):
    if logs.empty: return logs
    return logs[logs["id"].astype(str).str.strip().str.upper()==cid(emp_id)]

def today_rows(logs, emp_id):
    rows = employee_rows(logs, emp_id)
    return rows[rows["work_date"].astype(str) == str(chicago_today())] if not rows.empty else rows

def last_row_for_employee(logs, emp_id):
    rows = today_rows(logs, emp_id)
    if rows.empty: rows = employee_rows(logs, emp_id)
    if rows.empty: return None
    return rows.iloc[-1]

def msg(kind, text):
    cls = {"good":"good","warn":"warn","err":"err"}[kind]
    st.markdown(f"<div class='{cls}'>{text}</div>", unsafe_allow_html=True)

def detail_box(label, value):
    st.markdown(f"<div class='detail-box'><div class='detail-label'>{label}</div><div class='detail-value'>{value}</div></div>", unsafe_allow_html=True)

def append_audit(audit_ws, action, emp=None, status="", message="", notes=""):
    t = now_text()
    if emp is None:
        row = [t, action, "", "", "", status, message, notes]
    else:
        row = [t, action, cid(emp.get("id","")), emp.get("name",""), emp.get("team",""), status, message, notes]
    audit_ws.append_row([str(x) for x in row])

def backup_attendance(attendance_ws, backup_ws, reason):
    vals = attendance_ws.get_all_values()
    if len(vals) <= 1:
        backup_ws.append_row([now_text(), reason] + [""] * len(LOG_HEADERS))
        return
    rows, t = [], now_text()
    for r in vals[1:]:
        r = (r + [""] * len(LOG_HEADERS))[:len(LOG_HEADERS)]
        if str(r[0]).strip().lower() in ["", "id"]: continue
        rows.append([t, reason] + r)
    if rows: backup_ws.append_rows(rows)

def append_attendance(log_ws, row_dict):
    log_ws.append_row([str(row_dict.get(h, "")) for h in LOG_HEADERS])

def update_attendance_row(log_ws, sheet_row, updates):
    header_pos = {h: i+1 for i, h in enumerate(LOG_HEADERS)}
    for key, val in updates.items():
        if key in header_pos:
            log_ws.update_cell(int(sheet_row), header_pos[key], str(val))

def report_base(logs):
    df = calc_logs(logs.drop(columns=["_row"], errors="ignore")).copy()
    if df.empty: return df
    df["work_date_dt"] = pd.to_datetime(df["work_date"], errors="coerce")
    df["work_num"] = pd.to_numeric(df["work_hours"], errors="coerce").fillna(0)
    df["break_num"] = pd.to_numeric(df["break_hours"], errors="coerce").fillna(0)
    return df

def summarize_report(df, start_date, end_date, group_type):
    if df.empty:
        return pd.DataFrame(columns=["id","name","team","total_work_hours","total_break_hours","shifts"])
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    sub = df[(df["work_date_dt"] >= start) & (df["work_date_dt"] <= end)].copy()

    if group_type == "local":
        sub = sub[
            sub["name"].isin(LOCAL_NAMES) |
            sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS)
        ]
    elif group_type == "remote":
        sub = sub[
            sub["team"].astype(str).str.lower().isin(REMOTE_TEAMS) |
            (~sub["name"].isin(LOCAL_NAMES) & ~sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS))
        ]

    if sub.empty:
        return pd.DataFrame(columns=["id","name","team","total_work_hours","total_break_hours","shifts"])

    summary = sub.groupby(["id","name","team"], as_index=False).agg(
        total_work_hours=("work_num","sum"),
        total_break_hours=("break_num","sum"),
        shifts=("id","count")
    )
    summary["total_work_hours"] = summary["total_work_hours"].round(2)
    summary["total_break_hours"] = summary["total_break_hours"].round(2)

    if group_type == "local":
        summary["hourly_rate"] = summary["name"].map(HOURLY_RATES).fillna(0).astype(float)
        summary["weekly_salary"] = (summary["total_work_hours"].astype(float) * summary["hourly_rate"]).round(2)
    return summary

def save_payroll_snapshot(archive_ws, summary, report_type, start_date, end_date, notes=""):
    if summary.empty:
        return 0
    rows = []
    stamp = now_text()
    for _, r in summary.iterrows():
        rows.append([
            stamp, report_type, str(start_date), str(end_date),
            str(r.get("id","")), str(r.get("name","")), str(r.get("team","")),
            str(r.get("total_work_hours","")), str(r.get("total_break_hours","")),
            str(r.get("shifts","")), notes
        ])
    archive_ws.append_rows(rows)
    return len(rows)


def details_for_range(base, start_date, end_date, group_type):
    if base.empty:
        return pd.DataFrame()
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    sub = base[(base["work_date_dt"] >= start) & (base["work_date_dt"] <= end)].copy()
    if group_type == "local":
        sub = sub[sub["name"].isin(LOCAL_NAMES) | sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS)]
    elif group_type == "remote":
        sub = sub[sub["team"].astype(str).str.lower().isin(REMOTE_TEAMS) | (~sub["name"].isin(LOCAL_NAMES) & ~sub["team"].astype(str).str.lower().isin(LOCAL_TEAMS))]
    return sub.drop(columns=["work_date_dt","work_num","break_num","_row"], errors="ignore")

def excel_bytes(summary_df, detail_df, report_title, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        info = pd.DataFrame({
            "Report": [report_title],
            "Period Start": [str(start_date)],
            "Period End": [str(end_date)],
            "Created": [now_text()]
        })
        info.to_excel(writer, sheet_name="Report Info", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        detail_df.to_excel(writer, sheet_name="Shift Details", index=False)
        wb = writer.book
        for ws in wb.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val = "" if cell.value is None else str(cell.value)
                    max_len = max(max_len, len(val))
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 36)
        if "Summary" in wb.sheetnames and not summary_df.empty:
            ws = wb["Summary"]
            total_row = ws.max_row + 1
            ws.cell(total_row, 1).value = "TOTAL"
            cols = {cell.value: cell.column for cell in ws[1]}
            if "total_work_hours" in cols:
                ws.cell(total_row, cols["total_work_hours"]).value = float(pd.to_numeric(summary_df["total_work_hours"], errors="coerce").fillna(0).sum())
            if "total_break_hours" in cols:
                ws.cell(total_row, cols["total_break_hours"]).value = float(pd.to_numeric(summary_df["total_break_hours"], errors="coerce").fillna(0).sum())
            if "shifts" in cols:
                ws.cell(total_row, cols["shifts"]).value = int(pd.to_numeric(summary_df["shifts"], errors="coerce").fillna(0).sum())
    output.seek(0)
    return output.getvalue()

try:
    sheet = connect_sheet()
    emp_ws = get_ws(sheet, "Employees", EMP_HEADERS)
    log_ws = get_ws(sheet, "Attendance", LOG_HEADERS)
    backup_ws = get_ws(sheet, "Attendance_Backup", BACKUP_HEADERS)
    audit_ws = get_ws(sheet, "AuditLog", AUDIT_HEADERS)
    payroll_archive_ws = get_ws(sheet, "Payroll_Archive", PAYROLL_ARCHIVE_HEADERS)
except Exception as e:
    st.error("Google Sheet connection failed.")
    st.code(str(e))
    st.stop()

employees = read_ws(emp_ws, EMP_HEADERS)
logs = calc_logs(read_ws(log_ws, LOG_HEADERS, keep_row_number=True))

page = st.sidebar.radio("Page", ["Employee Clock", "Admin", "Payroll"])

if page == "Employee Clock":
    st.markdown("<div class='main-shell'>", unsafe_allow_html=True)
    h1, h2 = st.columns([3,1])
    with h1:
        st.markdown("""
        <div class="header-card">
          <div style="display:flex;align-items:center;gap:16px;">
            <div class="logo-box">ES</div>
            <div>
              <div style="font-size:32px;font-weight:900;color:#0f172a;">Egala Spot</div>
              <div style="color:#2563eb;font-weight:900;">Office In • Break • Office Out</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with h2:
        st.markdown(f"<div class='time-card'><div class='time-small'>CURRENT TIME</div><div class='time-big'>{display_now()}</div><div class='time-date'>{display_date()}</div></div>", unsafe_allow_html=True)

    active = active_employees(employees)
    if active.empty:
        st.error("No active employees found.")
        st.stop()

    st.markdown("<div class='form-card'>", unsafe_allow_html=True)
    c_emp, c_pin = st.columns([2,1])
    with c_emp:
        selected_name = st.selectbox("Employee", active["name"].astype(str).tolist())
    with c_pin:
        pin = st.text_input("PIN", type="password", placeholder="Enter PIN")
    notes = st.text_input("Optional Notes", placeholder="Optional - leave blank for normal punch")

    emp_row = find_emp_by_name_pin(employees, selected_name, pin) if pin else None
    status, last_action = "Enter PIN", "-"
    if emp_row is not None:
        cur = open_shift(logs, emp_row["id"])
        if cur.empty:
            status = "Not in office"
            lr = last_row_for_employee(logs, emp_row["id"])
            if lr is not None: last_action = str(lr.get("status","-")) or "-"
        else:
            r = cur.iloc[-1]
            status = "On Break" if str(r["break_start"]).strip() and not str(r["break_end"]).strip() else "In Office"
            last_action = status

    a1, a2, a3, a4 = st.columns(4)

    def need_emp():
        emp = find_emp_by_name_pin(employees, selected_name, pin)
        if emp is None:
            msg("err", "Wrong PIN.")
            return None
        return emp

    if a1.button("✅ Office In", use_container_width=True):
        emp = need_emp()
        if emp is not None:
            cur = open_shift(logs, emp["id"])
            if not cur.empty:
                append_audit(audit_ws, "Office In Blocked", emp, "Blocked", "Already in office", notes)
                msg("err", "Already in office.")
            else:
                backup_attendance(log_ws, backup_ws, "Before Office In")
                t = now_text()
                row = {"id":cid(emp["id"]), "name":emp["name"], "team":emp["team"], "work_date":str(chicago_today()), "punch_in":t, "break_start":"", "break_end":"", "punch_out":"", "break_hours":"", "work_hours":"", "status":"Working", "notes":notes}
                append_attendance(log_ws, row)
                append_audit(audit_ws, "Office In", emp, "Working", f"Office In saved at {nice_time(t)}", notes)
                logs = pd.concat([logs, pd.DataFrame([row])], ignore_index=True)
                status, last_action = "In Office", "Office In"
                msg("good", f"Office In saved at {nice_time(t)}")

    if a2.button("☕ Start Break", use_container_width=True):
        emp = need_emp()
        if emp is not None:
            cur = open_shift(logs, emp["id"])
            if cur.empty:
                append_audit(audit_ws, "Start Break Blocked", emp, "Blocked", "Office In first", notes)
                msg("warn", "Office In first.")
            else:
                i = cur.index[-1]; sheet_row = logs.at[i, "_row"]
                bs, be = str(logs.at[i,"break_start"]).strip(), str(logs.at[i,"break_end"]).strip()
                if not bs:
                    backup_attendance(log_ws, backup_ws, "Before Start Break")
                    t = now_text()
                    update_attendance_row(log_ws, sheet_row, {"break_start": t, "status": "On Break"})
                    append_audit(audit_ws, "Start Break", emp, "On Break", f"Break started at {nice_time(t)}", notes)
                    logs.at[i,"break_start"], logs.at[i,"status"] = t, "On Break"
                    status, last_action = "On Break", "Start Break"
                    msg("good", f"Break started at {nice_time(t)}")
                elif not be:
                    append_audit(audit_ws, "Start Break Blocked", emp, "Blocked", "Already on break", notes)
                    msg("warn", "Already on break.")
                else:
                    append_audit(audit_ws, "Start Break Blocked", emp, "Blocked", "Break already completed", notes)
                    msg("warn", "Break already completed.")

    if a3.button("↩ End Break", use_container_width=True):
        emp = need_emp()
        if emp is not None:
            cur = open_shift(logs, emp["id"])
            if cur.empty:
                append_audit(audit_ws, "End Break Blocked", emp, "Blocked", "No active office time", notes)
                msg("warn", "No active office time.")
            else:
                i = cur.index[-1]; sheet_row = logs.at[i, "_row"]
                bs, be = str(logs.at[i,"break_start"]).strip(), str(logs.at[i,"break_end"]).strip()
                if not bs:
                    append_audit(audit_ws, "End Break Blocked", emp, "Blocked", "No break started", notes)
                    msg("warn", "No break started.")
                elif not be:
                    backup_attendance(log_ws, backup_ws, "Before End Break")
                    t = now_text()
                    logs.at[i,"break_end"], logs.at[i,"status"] = t, "Working"
                    logs = calc_logs(logs)
                    update_attendance_row(log_ws, sheet_row, {"break_end": t, "break_hours": logs.at[i,"break_hours"], "work_hours": logs.at[i,"work_hours"], "status": "Working"})
                    append_audit(audit_ws, "End Break", emp, "Working", f"Break ended at {nice_time(t)}", notes)
                    status, last_action = "In Office", "End Break"
                    msg("good", f"Break ended at {nice_time(t)}")
                else:
                    append_audit(audit_ws, "End Break Blocked", emp, "Blocked", "Break already ended", notes)
                    msg("warn", "Break already ended.")

    if a4.button("🚪 Office Out", use_container_width=True):
        emp = need_emp()
        if emp is not None:
            cur = open_shift(logs, emp["id"])
            if cur.empty:
                append_audit(audit_ws, "Office Out Blocked", emp, "Blocked", "No active office time", notes)
                msg("warn", "No active office time.")
            else:
                i = cur.index[-1]; sheet_row = logs.at[i, "_row"]
                bs, be = str(logs.at[i,"break_start"]).strip(), str(logs.at[i,"break_end"]).strip()
                if bs and not be:
                    append_audit(audit_ws, "Office Out Blocked", emp, "Blocked", "End break first", notes)
                    msg("err", "End break first.")
                else:
                    backup_attendance(log_ws, backup_ws, "Before Office Out")
                    t = now_text()
                    logs.at[i,"punch_out"], logs.at[i,"status"] = t, "Completed"
                    logs = calc_logs(logs)
                    update_attendance_row(log_ws, sheet_row, {"punch_out": t, "break_hours": logs.at[i,"break_hours"], "work_hours": logs.at[i,"work_hours"], "status": "Completed"})
                    append_audit(audit_ws, "Office Out", emp, "Completed", f"Office Out saved at {nice_time(t)}", notes)
                    status, last_action = "Not in office", "Office Out"
                    msg("good", f"Office Out saved at {nice_time(t)}")

    st.markdown(f"<div class='status-bar'>Status: {status}</div>", unsafe_allow_html=True)
    today_count = len(logs[logs["work_date"].astype(str)==str(chicago_today())]) if not logs.empty else 0
    open_count = len(logs[logs["punch_out"].astype(str).str.strip()==""]) if not logs.empty else 0
    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Today Punches</div><div class='metric-value'>{today_count}</div></div>", unsafe_allow_html=True)
    with m2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Open Shifts</div><div class='metric-value'>{open_count}</div></div>", unsafe_allow_html=True)
    with m3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Last Action</div><div class='metric-value'>{last_action}</div></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='details-card'><div class='details-title'>Employee Shift Details</div>", unsafe_allow_html=True)
    if not pin:
        st.info("Enter PIN to view your shift details.")
    elif emp_row is None:
        st.warning("Correct PIN required to view shift details.")
    else:
        lr = last_row_for_employee(logs, emp_row["id"])
        if lr is None:
            st.info("No shift record found yet. Click Office In to start your shift.")
        else:
            d1, d2, d3, d4 = st.columns(4)
            with d1: detail_box("Office In", nice_time(lr.get("punch_in","")))
            with d2: detail_box("Break Start", nice_time(lr.get("break_start","")))
            with d3: detail_box("Break End", nice_time(lr.get("break_end","")))
            with d4: detail_box("Office Out", nice_time(lr.get("punch_out","")))
            d5, d6, d7, d8 = st.columns(4)
            with d5: detail_box("Work Hours", str(lr.get("work_hours","") or "-"))
            with d6: detail_box("Break Hours", str(lr.get("break_hours","") or "-"))
            with d7: detail_box("Status", str(lr.get("status","") or "-"))
            with d8: detail_box("Team", str(lr.get("team","") or "-"))
    st.markdown("</div></div>", unsafe_allow_html=True)

elif page == "Admin":
    st.title("Egala Spot Admin")
    admin_pin = st.sidebar.text_input("Admin PIN", type="password")
    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()
    t1, t2, t3, t4, t5 = st.tabs(["Employees", "Attendance", "AuditLog", "Backup", "Payroll Archive"])
    with t1:
        st.dataframe(employees.drop(columns=["pin"], errors="ignore"), use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(logs.drop(columns=["_row"], errors="ignore"), use_container_width=True, hide_index=True)
        st.download_button("Download Attendance CSV", logs.drop(columns=["_row"], errors="ignore").to_csv(index=False).encode("utf-8"), "attendance.csv", "text/csv")
    with t3:
        audit = read_ws(audit_ws, AUDIT_HEADERS)
        st.dataframe(audit, use_container_width=True, hide_index=True)
        st.download_button("Download AuditLog CSV", audit.to_csv(index=False).encode("utf-8"), "audit_log.csv", "text/csv")
    with t4:
        backup = read_ws(backup_ws, BACKUP_HEADERS)
        st.dataframe(backup, use_container_width=True, hide_index=True)
        st.download_button("Download Backup CSV", backup.to_csv(index=False).encode("utf-8"), "attendance_backup.csv", "text/csv")
    with t5:
        archive = read_ws(payroll_archive_ws, PAYROLL_ARCHIVE_HEADERS)
        st.dataframe(archive, use_container_width=True, hide_index=True)
        st.download_button("Download Payroll Archive CSV", archive.to_csv(index=False).encode("utf-8"), "payroll_archive.csv", "text/csv")

elif page == "Payroll":
    st.title("Egala Spot Payroll")
    admin_pin = st.sidebar.text_input("Admin PIN", type="password")
    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN.")
        st.stop()

    base = report_base(logs)
    today = chicago_today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    st.subheader("Weekly Local Report")
    c1, c2 = st.columns(2)
    with c1:
        local_start = st.date_input("Local Week Start", value=week_start)
    with c2:
        local_end = st.date_input("Local Week End", value=week_end)

    local_summary = summarize_report(base, local_start, local_end, "local")
    local_details = details_for_range(base, local_start, local_end, "local")
    st.dataframe(local_summary, use_container_width=True, hide_index=True)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Save Weekly Local Payroll Snapshot", use_container_width=True):
            n = save_payroll_snapshot(payroll_archive_ws, local_summary, "Weekly Local", local_start, local_end, "Local weekly snapshot")
            append_audit(audit_ws, "Payroll Snapshot", None, "Saved", f"Weekly Local snapshot saved: {n} rows", "")
            st.success(f"Saved {n} local payroll rows to Payroll_Archive.")
    with b2:
        st.download_button(
            "Download Weekly Local Payroll Excel",
            excel_bytes(local_summary, local_details, "Weekly Local Payroll", local_start, local_end),
            f"weekly_local_payroll_{local_start}_to_{local_end}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.divider()

    st.subheader("Monthly Overseas Report")
    month_start_default = today.replace(day=10)
    if today.day < 10:
        prev_month = (today.replace(day=1) - timedelta(days=1))
        month_start_default = prev_month.replace(day=10)
    next_month_anchor = (month_start_default.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end_default = next_month_anchor.replace(day=9)

    c3, c4 = st.columns(2)
    with c3:
        remote_start = st.date_input("Overseas Period Start", value=month_start_default)
    with c4:
        remote_end = st.date_input("Overseas Period End", value=month_end_default)

    remote_summary = summarize_report(base, remote_start, remote_end, "remote")
    remote_details = details_for_range(base, remote_start, remote_end, "remote")
    st.dataframe(remote_summary, use_container_width=True, hide_index=True)

    b3, b4 = st.columns(2)
    with b3:
        if st.button("Save Monthly Overseas Payroll Snapshot", use_container_width=True):
            n = save_payroll_snapshot(payroll_archive_ws, remote_summary, "Monthly Overseas", remote_start, remote_end, "Overseas monthly snapshot")
            append_audit(audit_ws, "Payroll Snapshot", None, "Saved", f"Monthly Overseas snapshot saved: {n} rows", "")
            st.success(f"Saved {n} overseas payroll rows to Payroll_Archive.")
    with b4:
        st.download_button(
            "Download Monthly Overseas Payroll Excel",
            excel_bytes(remote_summary, remote_details, "Monthly Overseas Payroll", remote_start, remote_end),
            f"monthly_overseas_payroll_{remote_start}_to_{remote_end}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.divider()

    st.subheader("All Completed Shift Details")
    if base.empty:
        st.info("No attendance data yet.")
    else:
        all_details = base.drop(columns=["work_date_dt","work_num","break_num","_row"], errors="ignore")
        st.dataframe(all_details, use_container_width=True, hide_index=True)
        st.download_button(
            "Download All Shift Details Excel",
            excel_bytes(all_details, all_details, "All Shift Details", "", ""),
            "all_shift_details.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )


st.markdown('''<style>
.stSelectbox label{
    font-size:24px !important;
    font-weight:900 !important;
}
.stTextInput label{
    font-size:24px !important;
    font-weight:900 !important;
}
.stButton>button{
    font-size:28px !important;
    font-weight:900 !important;
    height:82px !important;
}
.st.columns(4){
    font-size: 28px;
}
p{
font-size:24px;
}

</style>''', unsafe_allow_html=True)
