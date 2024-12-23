import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Google Sheets document IDs and ranges
RECEPTION_SHEET_ID = '1Y3uYVe_A7w00_AfywqprA7qolsf8CMOvgrUHV3hmB6E'
RECEPTION_SHEET_RANGE = 'Sheet1'

LOGIN_LOG_SHEET_ID = '1u6M5pQyeDg44QXynb79YP9Mf1V6JlIqqthKrVx-DAfA'
LOGIN_LOG_SHEET_RANGE = 'Sheet1'

NHANVIEN_SHEET_ID = '1kzfwjA0nVLFoW8T5jroLyR2lmtdZp8eaYH-_Pyb0nbk'
NHANVIEN_SHEET_RANGE = 'Sheet1'

# Load Google credentials from Streamlit Secrets
google_credentials = st.secrets["GOOGLE_CREDENTIALS"]
credentials_info = json.loads(google_credentials)

# Authenticate using the service account credentials
credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

# Initialize the Google Sheets API client
sheets_service = build('sheets', 'v4', credentials=credentials)


def fetch_sheet_data(sheet_id, range_name):
    """Fetches data from Google Sheets and returns it as a DataFrame."""
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()
    values = result.get('values', [])
    
    if not values:
        return pd.DataFrame()  # Return an empty DataFrame if no data is found
    
    headers = values[0]
    rows = values[1:]
    normalized_rows = [row + [''] * (len(headers) - len(row)) for row in rows]
    return pd.DataFrame(normalized_rows, columns=headers)


def append_to_sheet(sheet_id, range_name, values):
    """Appends data to a Google Sheet."""
    body = {'values': values}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def log_user_activity(ten_nhan_vien, table, login_time=None, logout_time=None):
    """Logs user activity (login or logout) in a Google Sheet."""
    data = [[ten_nhan_vien, table, login_time, logout_time]]
    append_to_sheet(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE, data)


def is_table_available(table):
    """Checks if the table is already assigned to another user."""
    login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)
    if login_log_df.empty:
        return True  # No assignments yet

    active_assignments = login_log_df[(login_log_df["Table"] == str(table)) & login_log_df["thoiGianLogout"].isna()]
    return active_assignments.empty  # Table is available if no active assignments


def display_login_page():
    """Displays the login page."""
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Fetch all available tables
    available_tables = [table for table in range(1, 6) if is_table_available(table)]
    if not available_tables:
        st.error("All tables are currently assigned. Please wait for availability.")
        return

    # Dropdown for table selection (only available tables)
    table = st.selectbox("Select Table", options=available_tables)

    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
        user = nhanvien_df[(nhanvien_df['taiKhoan'] == username) & (nhanvien_df['matKhau'] == password)]
        if not user.empty:
            user_info = user.iloc[0].to_dict()
            st.session_state['is_logged_in'] = True
            st.session_state['user_info'] = user_info
            st.session_state['table'] = table  # Store selected table
            st.success(f"Welcome, {user_info['tenNhanVien']}!")

            # Log login activity
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            login_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
            log_user_activity(user_info['tenNhanVien'], table, login_time=login_time)

        else:
            st.error("Invalid username or password.")


def display_logout():
    """Logs out the user and records the logout time."""
    user_info = st.session_state['user_info']
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

    # Log logout activity
    log_user_activity(user_info['tenNhanVien'], st.session_state['table'], logout_time=logout_time)

    # Clear session state
    st.session_state.clear()
    st.success("You have been logged out.")


def display_registration_tab():
    """Displays the New Registration tab."""
    st.title("Register New PID")
    
    pid = st.text_input("Enter PID:")
    user_info = st.session_state.get("user_info", {})
    table = st.session_state.get("table", None)
    
    if st.button("Register PID"):
        if pid:
            # Get the current timestamp
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

            # Data to append
            data = [[pid, "Patient Name", timestamp, user_info.get("tenNhanVien", ""), "", "", table]]
            append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, data)

            st.success(f"PID {pid} registered successfully.")
        else:
            st.error("Please enter a PID.")


def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.write("### Reception Management")

    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    user_name = st.session_state["user_info"]["tenNhanVien"]

    # Filter rows where 'thoiGianLayMau' is empty or 'nguoiLayMau' matches the logged-in user
    filtered_df = reception_df[
        reception_df["thoiGianLayMau"].isna() | (reception_df["nguoiLayMau"] == user_name)
    ]

    filtered_df["thoiGianNhanMau"] = pd.to_datetime(filtered_df["thoiGianNhanMau"], errors="coerce")
    filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

    # Rename columns
    filtered_df = filtered_df.rename(columns={
        "PID": "PID",
        "tenBenhNhan": "Họ tên",
        "thoiGianNhanMau": "Thời gian nhận mẫu",
        "thoiGianLayMau": "Thời gian lấy máu",
        "nguoiLayMau": "Người lấy máu",
        "table": "Table",
    })

    st.dataframe(filtered_df, use_container_width=True)

    # Mark as Received functionality
    selectable_pids = filtered_df[filtered_df["Thời gian lấy máu"].isna()]["PID"].tolist()
    if selectable_pids:
        selected_pid = st.selectbox("Select a PID to mark as received:", selectable_pids)
        if st.button("Mark as Received"):
            now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            filtered_df.loc[filtered_df["PID"] == selected_pid, "Thời gian lấy máu"] = now
            filtered_df.loc[filtered_df["PID"] == selected_pid, "Người lấy máu"] = user_name

            st.success(f"PID {selected_pid} marked as received.")


def main():
    if not st.session_state.get('is_logged_in', False):
        display_login_page()
    else:
        user_info = st.session_state['user_info']
        st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']}")

        selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception"])

        if selected_tab == "Register New PID":
            display_registration_tab()
        elif selected_tab == "Reception":
            display_reception_tab()

        if st.sidebar.button("Logout"):
            display_logout()


main()
