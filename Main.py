import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

# Google Sheets document IDs and ranges
RECEPTION_SHEET_ID = '1Y3uYVe_A7w00_AfywqprA7qolsf8CMOvgrUHV3hmB6E'
RECEPTION_SHEET_RANGE = 'Sheet1'
NHANVIEN_SHEET_ID = '1kzfwjA0nVLFoW8T5jroLyR2lmtdZp8eaYH-_Pyb0nbk'
NHANVIEN_SHEET_RANGE = 'Sheet1'
LOGIN_LOG_SHEET_ID = '1u6M5pQyeDg44QXynb79YP9Mf1V6JlIqqthKrVx-DAfA'
LOGIN_LOG_SHEET_RANGE = 'Sheet1'

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


def display_login_page():
    """Displays the login page."""
    st.title("Login")

    # Fetch login log data
    login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)
    all_tables = [str(i) for i in range(1, 6)]

    # Determine available tables
    if not login_log_df.empty:
        active_tables = login_log_df[login_log_df['thoiGianLogout'] == ""]["Table"].tolist()
        available_tables = [table for table in all_tables if table not in active_tables]
    else:
        available_tables = all_tables  # All tables are available if no log exists

    # Table selection dropdown
    selected_table = st.selectbox("Select a table to log in:", available_tables)

    # User credentials input
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
        user = nhanvien_df[(nhanvien_df['taiKhoan'] == username) & (nhanvien_df['matKhau'] == password)]

        if not user.empty:
            user_info = user.iloc[0].to_dict()
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            login_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

            # Save login details to the session
            st.session_state['is_logged_in'] = True
            st.session_state['user_info'] = user_info
            st.session_state['selected_table'] = selected_table

            # Append login information to the login log sheet
            append_to_sheet(
                LOGIN_LOG_SHEET_ID,
                LOGIN_LOG_SHEET_RANGE,
                [[user_info['tenNhanVien'], selected_table, login_time, ""]]
            )

            st.success(f"Welcome, {user_info['tenNhanVien']}! You are logged in at table {selected_table}.")
        else:
            st.error("Invalid username or password.")


def display_registration_tab():
    """Displays the New Registration tab."""
    st.title("Register New PID")
    
    pid = st.text_input("Enter PID:")
    user_info = st.session_state.get("user_info", {})
    
    if st.button("Register PID"):
        if pid:
            # Fetch patient name (dummy implementation for now)
            patient_name = f"Patient {pid}"  # Replace with API call
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
            append_to_sheet(
                RECEPTION_SHEET_ID,
                RECEPTION_SHEET_RANGE,
                [[pid, patient_name, timestamp, user_info['tenNhanVien'], "", ""]]
            )
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

    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    user_name = st.session_state["user_info"]["tenNhanVien"]
    reception_df = reception_df.replace("", None)

    filtered_df = reception_df[
        reception_df["thoiGianLayMau"].isna() | (reception_df["nguoiLayMau"] == user_name)
    ]
    filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

    st.write("### Patients for Current Receptionist")
    st.dataframe(filtered_df, use_container_width=True)

    if not filtered_df.empty:
        selected_pid = st.selectbox("Select a PID to mark as received:", filtered_df["PID"].tolist())
        if st.button("Mark as Received"):
            reception_df.loc[reception_df["PID"] == selected_pid, "thoiGianLayMau"] = datetime.now(
                pytz.timezone("Asia/Ho_Chi_Minh")
            ).strftime("%Y-%m-%d %H:%M:%S")
            reception_df.loc[reception_df["PID"] == selected_pid, "nguoiLayMau"] = user_name

            updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
            sheets_service.spreadsheets().values().update(
                spreadsheetId=RECEPTION_SHEET_ID,
                range=RECEPTION_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                body={"values": updated_values}
            ).execute()
            st.success(f"PID {selected_pid} marked as received.")
    else:
        st.write("No patients to mark as received.")


# Main App Logic
if not st.session_state.get('is_logged_in', False):
    display_login_page()
else:
    user_info = st.session_state['user_info']
    st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']} (Table {st.session_state['selected_table']})")

    selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception"])
    if selected_tab == "Register New PID":
        display_registration_tab()
    elif selected_tab == "Reception":
        display_reception_tab()

    if st.sidebar.button("Logout"):
        st.session_state.clear()
