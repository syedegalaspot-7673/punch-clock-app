
import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials

SHEET_ID = "1PIYrwnqIwSNcCdAfNLniGuhCYoIe3YUbpQzXTYxCovw"
CREDENTIALS_FILE = "credentials.json"
ADMIN_PIN = "9999"

EMP_HEADERS = ["id", "name", "pin", "team", "active"]
LOG_HEADERS = [
    "id", "name", "team", "work_date",
    "punch_in", "break_start", "break_end", "punch_out",
    "break_hours", "work_hours", "status", "notes"
]

st.set_page_config(page_title="Punch Clock Locked", layout="wide")

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def cid(x):
    return str(x).strip().upper()

@st.cache_resource
def connect_sheet():
    if not Path(CREDENTIALS_FILE).exists():
        st.error("credentials.json missing. Put it in the same folder as app.py.")
        st.stop()

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

def get_ws(sheet, name, headers):
    try:
        ws = sheet.worksheet(name)
    except WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=3000, cols=max(len(headers), 20))
        ws.append_row(headers)
        return ws

    vals = ws.get_all_values()
    if not vals:
        ws.append_row(headers)
    elif vals[0] != headers:
        old = vals[1:]
        ws.clear()
        ws.append_row(headers)
        if old:
            fixed = [(r + [""] * len(headers))[:len(headers)] for r in old]
            ws.append_rows(fixed)

    return ws

def read_ws(ws, headers):
    vals = ws.get_all_values()

    if len(vals) <= 1:
        return pd.DataFrame(columns=headers)

    rows = []
    for r in vals[1:]:
        r = (r + [""] * len(headers))[:len(headers)]
        if r == headers:
            continue
        if r[0].strip().lower() in ["", "id"]:
            continue
        rows.append(r)

    return pd.DataFrame(rows, columns=headers).fillna("")

def save_ws(ws, df, headers):
    ws.clear()
    ws.append_row(headers)

    if not df.empty:
        ws.append_rows(df[headers].astype(str).values.tolist())

def safe_dt(x):
    x = str(x).strip()

    if x == "" or x.lower() in ["none", "nan"]:
        return None

    v = pd.to_datetime(x, errors="coerce")
    return None if pd.isna(v) else v

def calc_logs(df):
    if df.empty:
        return df

    for i, r in df.iterrows():
        pi = safe_dt(r.get("punch_in", ""))
        po = safe_dt(r.get("punch_out", ""))
        bs = safe_dt(r.get("break_start", ""))
        be = safe_dt(r.get("break_end", ""))

        break_hours = ""
        work_hours = ""

        if bs is not None and be is not None:
            break_hours = round(max((be - bs).total_seconds() / 3600, 0), 2)

        if pi is not None and po is not None:
            gross = max((po - pi).total_seconds() / 3600, 0)
            break_num = float(break_hours) if break_hours != "" else 0
            work_hours = round(max(gross - break_num, 0), 2)

        df.loc[i, "break_hours"] = break_hours
        df.loc[i, "work_hours"] = work_hours

    return df

def active_employees(df):
    if df.empty:
        return df

    e = df.copy()
    e["active"] = e["active"].astype(str).str.lower().str.strip()
    return e[e["active"].isin(["true", "yes", "1", "active"])]

def find_emp_by_name_pin(emp, name, pin):
    e = active_employees(emp)

    if e.empty:
        return None

    m = e[
        (e["name"].astype(str) == str(name)) &
        (e["pin"].astype(str).str.strip() == str(pin).strip())
    ]

    return None if m.empty else m.iloc[0]

def open_shift(logs, emp_id):
    if logs.empty:
        return logs

    return logs[
        (logs["id"].astype(str).str.strip().str.upper() == cid(emp_id)) &
        (logs["punch_out"].astype(str).str.strip() == "")
    ]

def seed_employee_if_empty(emp_ws):
    emp = read_ws(emp_ws, EMP_HEADERS)

    if emp.empty:
        sample = pd.DataFrame([
            {"id": "1", "name": "John", "pin": "1234", "team": "WH", "active": "TRUE"},
        ])
        save_ws(emp_ws, sample, EMP_HEADERS)

try:
    sheet = connect_sheet()
    emp_ws = get_ws(sheet, "Employees", EMP_HEADERS)
    log_ws = get_ws(sheet, "Attendance", LOG_HEADERS)
    seed_employee_if_empty(emp_ws)
except Exception as e:
    st.error("Google Sheet connection failed.")
    st.code(str(e))
    st.stop()

employees = read_ws(emp_ws, EMP_HEADERS)
logs = calc_logs(read_ws(log_ws, LOG_HEADERS))
save_ws(log_ws, logs, LOG_HEADERS)

st.title("Punch Clock Locked")
page = st.sidebar.radio("Page", ["Employee Clock", "Admin", "Payroll"])

if page == "Employee Clock":
    st.header("Employee Clock")

    active = active_employees(employees)
    if active.empty:
        st.error("No active employees found. Add employees in Admin.")
        st.stop()

    selected_name = st.selectbox("Employee", active["name"].astype(str).tolist())
    pin = st.text_input("PIN", type="password")
    notes = st.text_input("Optional notes")

    emp_row = find_emp_by_name_pin(employees, selected_name, pin) if pin else None

    if emp_row is not None:
        cur = open_shift(logs, emp_row["id"])
        if cur.empty:
            status = "Not punched in"
        else:
            r = cur.iloc[-1]
            if str(r["break_start"]).strip() != "" and str(r["break_end"]).strip() == "":
                status = "On Break"
            else:
                status = "Working"
        st.info(f"Current status: {status}")

    c1, c2, c3, c4 = st.columns(4)

    if c1.button("Punch In", use_container_width=True):
        emp_row = find_emp_by_name_pin(employees, selected_name, pin)

        if emp_row is None:
            st.error("Wrong PIN.")

        else:
            cur = open_shift(logs, emp_row["id"])

            if not cur.empty:
                st.error("Already punched in. Punch out first.")

            else:
                t = now_text()
                new = pd.DataFrame([{
                    "id": cid(emp_row["id"]),
                    "name": emp_row["name"],
                    "team": emp_row["team"],
                    "work_date": str(date.today()),
                    "punch_in": t,
                    "break_start": "",
                    "break_end": "",
                    "punch_out": "",
                    "break_hours": "",
                    "work_hours": "",
                    "status": "Working",
                    "notes": notes
                }])

                logs = pd.concat([logs, new], ignore_index=True)
                save_ws(log_ws, logs, LOG_HEADERS)
                st.success(f"Punched in at {t}")

    if c2.button("Start Break", use_container_width=True):
        emp_row = find_emp_by_name_pin(employees, selected_name, pin)

        if emp_row is None:
            st.error("Wrong PIN.")

        else:
            cur = open_shift(logs, emp_row["id"])

            if cur.empty:
                st.warning("Punch in first.")

            else:
                i = cur.index[-1]
                bs = str(logs.loc[i, "break_start"]).strip()
                be = str(logs.loc[i, "break_end"]).strip()

                if bs == "":
                    t = now_text()
                    logs.loc[i, "break_start"] = t
                    logs.loc[i, "status"] = "On Break"
                    save_ws(log_ws, logs, LOG_HEADERS)
                    st.success(f"Break started at {t}")

                elif be == "":
                    st.warning("Break already started.")

                else:
                    st.warning("Break already completed for this shift.")

    if c3.button("End Break", use_container_width=True):
        emp_row = find_emp_by_name_pin(employees, selected_name, pin)

        if emp_row is None:
            st.error("Wrong PIN.")

        else:
            cur = open_shift(logs, emp_row["id"])

            if cur.empty:
                st.warning("No active shift.")

            else:
                i = cur.index[-1]
                bs = str(logs.loc[i, "break_start"]).strip()
                be = str(logs.loc[i, "break_end"]).strip()

                if bs == "":
                    st.warning("No break started.")

                elif be == "":
                    t = now_text()
                    logs.loc[i, "break_end"] = t
                    logs.loc[i, "status"] = "Working"
                    logs = calc_logs(logs)
                    save_ws(log_ws, logs, LOG_HEADERS)
                    st.success(f"Break ended at {t}")

                else:
                    st.warning("Break already ended.")

    if c4.button("Punch Out", use_container_width=True):
        emp_row = find_emp_by_name_pin(employees, selected_name, pin)

        if emp_row is None:
            st.error("Wrong PIN.")

        else:
            cur = open_shift(logs, emp_row["id"])

            if cur.empty:
                st.warning("No active shift.")

            else:
                i = cur.index[-1]
                bs = str(logs.loc[i, "break_start"]).strip()
                be = str(logs.loc[i, "break_end"]).strip()

                if bs != "" and be == "":
                    st.error("End break before punch out.")

                else:
                    t = now_text()
                    logs.loc[i, "punch_out"] = t
                    logs.loc[i, "status"] = "Completed"
                    logs = calc_logs(logs)
                    save_ws(log_ws, logs, LOG_HEADERS)
                    st.success(f"Punched out at {t}")

    fresh = calc_logs(read_ws(log_ws, LOG_HEADERS))

    st.subheader("Currently Working / On Break")
    active_rows = fresh[fresh["punch_out"].astype(str).str.strip() == ""]

    st.dataframe(
        active_rows[["id", "name", "team", "punch_in", "break_start", "break_end", "status"]],
        use_container_width=True
    )

    st.subheader("Recent Shift History")
    st.dataframe(
        fresh.tail(10)[["id", "name", "team", "work_date", "punch_in", "break_start", "break_end", "punch_out", "break_hours", "work_hours", "status"]],
        use_container_width=True
    )

elif page == "Admin":
    st.header("Admin")
    admin_pin = st.sidebar.text_input("Admin PIN", type="password")

    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN in sidebar.")
        st.stop()

    t1, t2, t3 = st.tabs(["Employees", "Add Employee", "Raw Attendance"])

    with t1:
        st.dataframe(employees.drop(columns=["pin"], errors="ignore"), use_container_width=True)

    with t2:
        nid = st.text_input("New Employee ID").strip()
        name = st.text_input("Employee Name").strip()
        epin = st.text_input("Employee PIN").strip()
        team = st.text_input("Team", value="WH").strip()
        is_active = st.selectbox("Active", ["TRUE", "FALSE"])

        if st.button("Add Employee"):
            if not nid or not name or not epin:
                st.error("ID, name, and PIN are required.")

            elif cid(nid) in employees["id"].astype(str).str.upper().str.strip().values:
                st.error("Employee ID already exists.")

            else:
                employees = pd.concat([
                    employees,
                    pd.DataFrame([{
                        "id": cid(nid),
                        "name": name,
                        "pin": epin,
                        "team": team,
                        "active": is_active
                    }])
                ], ignore_index=True)

                save_ws(emp_ws, employees, EMP_HEADERS)
                st.success("Employee added.")

    with t3:
        raw = calc_logs(read_ws(log_ws, LOG_HEADERS))
        st.dataframe(raw, use_container_width=True)
        st.download_button(
            "Download Attendance CSV",
            raw.to_csv(index=False).encode("utf-8"),
            "attendance.csv",
            "text/csv"
        )

elif page == "Payroll":
    st.header("Payroll")
    admin_pin = st.sidebar.text_input("Admin PIN", type="password")

    if admin_pin != ADMIN_PIN:
        st.warning("Enter admin PIN in sidebar.")
        st.stop()

    logs = calc_logs(read_ws(log_ws, LOG_HEADERS))
    completed = logs[logs["status"].astype(str).str.lower() == "completed"].copy()

    if completed.empty:
        st.info("No completed shifts yet.")
        st.stop()

    completed["work_num"] = pd.to_numeric(completed["work_hours"], errors="coerce").fillna(0)
    completed["break_num"] = pd.to_numeric(completed["break_hours"], errors="coerce").fillna(0)

    st.subheader("Completed Shifts")
    st.dataframe(completed.drop(columns=["work_num", "break_num"], errors="ignore"), use_container_width=True)

    summary = completed.groupby(["id", "name", "team"], as_index=False).agg(
        total_work_hours=("work_num", "sum"),
        total_break_hours=("break_num", "sum"),
        shifts=("id", "count")
    )

    summary["total_work_hours"] = summary["total_work_hours"].round(2)
    summary["total_break_hours"] = summary["total_break_hours"].round(2)

    st.subheader("Payroll Summary")
    st.dataframe(summary, use_container_width=True)

    st.download_button(
        "Download Payroll CSV",
        summary.to_csv(index=False).encode("utf-8"),
        "payroll_summary.csv",
        "text/csv"
    )
