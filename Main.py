import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Google Sheets document IDs and ranges
RECEPTION_SHEET_ID = '1Y3uYVe_A7w00_AfywqprA7qolsf8CMOvgrUHV3hmB6E'
RECEPTION_SHEET_RANGE = 'Sheet1'
LOGIN_LOG_SHEET_ID = '1u6M5pQyeDg44QXynb79YP9Mf1V6JlIqqthKrVx-DAfA'
LOGIN_LOG_SHEET_RANGE = 'Sheet1'
NHANVIEN_SHEET_ID = '1kzfwjA0nVLFoW8T5jroLyR2lmtdZp8eaYH-_Pyb0nbk'
NHANVIEN_SHEET_RANGE = 'Sheet1'

# Load Google credentials
google_credentials = st.secrets["GOOGLE_CREDENTIALS"]
credentials_info = json.loads(google_credentials)

credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

sheets_service = build('sheets', 'v4', credentials=credentials)


def fetch_sheet_data(sheet_id, range_name):
    """Fetches data from Google Sheets."""
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()
    values = result.get('values', [])
    headers = values[0] if values else []
    rows = values[1:] if values else []
    return pd.DataFrame(rows, columns=headers)


def append_to_sheet(sheet_id, range_name, values):
    """Appends data to Google Sheets."""
    body = {'values': values}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()


def fetch_patient_name(pid):
    """Fetches the patient name from the API."""
    url = f"https://api.bvhungvuong.vn/api/dangkykham/?ip=&idbv=&id=&mabn={pid}&ngay="
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        patient_data = data.get("data", [])
        if patient_data:
            return patient_data[0].get("hoten", "").strip()
    return None


def display_login_page():
    """Displays the login page."""
    st.title("Login")
    nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
    login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)

    # Determine available tables
    active_tables = login_log_df[login_log_df["thoiGianLogout"] == ""].get("Table", []).tolist()
    all_tables = [str(i) for i in range(1, 6)]
    available_tables = [table for table in all_tables if table not in active_tables]

    table_selection = st.selectbox("Select Table:", available_tables)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = nhanvien_df[(nhanvien_df["taiKhoan"] == username) & (nhanvien_df["matKhau"] == password)]
        if not user.empty:
            user_info = user.iloc[0].to_dict()
            st.session_state["is_logged_in"] = True
            st.session_state["user_info"] = user_info
            st.session_state["selected_table"] = table_selection

            # Log login event
            login_time = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            append_to_sheet(
                LOGIN_LOG_SHEET_ID,
                LOGIN_LOG_SHEET_RANGE,
                [[user_info["tenNhanVien"], table_selection, login_time, ""]]
            )
            st.success(f"Welcome, {user_info['tenNhanVien']} (Table {table_selection})!")
        else:
            st.error("Invalid credentials.")


def display_registration_tab():
    """Displays the Registration tab."""
    st.title("Register New PID")
    pid = st.text_input("Enter PID:")

    if st.button("Register PID"):
        user_info = st.session_state["user_info"]
        patient_name = fetch_patient_name(pid)
        if patient_name:
            timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            append_to_sheet(
                RECEPTION_SHEET_ID,
                RECEPTION_SHEET_RANGE,
                [[pid, patient_name, timestamp, user_info["tenNhanVien"], "", "", st.session_state["selected_table"]]]
            )
            st.success(f"PID {pid} registered successfully with patient name {patient_name}.")
        else:
            st.error("Failed to fetch patient name.")


def display_reception_tab():
    """Displays the Reception tab."""
    st.title("Reception")
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

    if not reception_df.empty:
        reception_df = reception_df.replace("", None)
        user_info = st.session_state["user_info"]

        # Filter rows where `thoiGianLayMau` is empty or assigned to current user
        filtered_df = reception_df[
            (reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLayMau"] == user_info["tenNhanVien"])
        ]
        filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

        st.dataframe(filtered_df[["PID", "tenBenhNhan", "thoiGianNhanMau"]])

        # Select and mark patient as received
        pid = st.selectbox("Select a PID to mark as received:", filtered_df["PID"].tolist())
        if st.button("Mark as Received"):
            timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            reception_df.loc[reception_df["PID"] == pid, "thoiGianLayMau"] = timestamp
            reception_df.loc[reception_df["PID"] == pid, "nguoiLayMau"] = user_info["tenNhanVien"]
            reception_df.loc[reception_df["PID"] == pid, "Table"] = st.session_state["selected_table"]

            updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
            sheets_service.spreadsheets().values().update(
                spreadsheetId=RECEPTION_SHEET_ID,
                range=RECEPTION_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                body={"values": updated_values}
            ).execute()
            st.success(f"PID {pid} marked as received.")


# Main
if "is_logged_in" not in st.session_state:
    display_login_page()
else:
    user_info = st.session_state["user_info"]
    st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']} (Table {st.session_state['selected_table']})")
    selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception"])

    if selected_tab == "Register New PID":
        display_registration_tab()
    elif selected_tab == "Reception":
        display_reception_tab()

    if st.sidebar.button("Logout"):
        st.session_state.clear()
