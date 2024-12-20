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
    
    # Ensure all rows match the number of headers
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

def register_pid(pid, ten_nhan_vien):
    """Registers a new PID."""
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = [[pid, timestamp, ten_nhan_vien, "", ""]]  # Empty values for 'thoiGianLayMau' and 'nguoiLayMau'
    append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, data)
    st.session_state['last_registered_pid'] = pid  # Store the last registered PID for updates

def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.write("### Reception Management")

    # Refresh button logic
    if st.button("Refresh"):
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    else:
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    required_columns = {"PID", "thoiGianNhanMau", "nguoiNhan", "thoiGianLayMau", "nguoiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    reception_df["thoiGianNhanMau"] = pd.to_datetime(reception_df["thoiGianNhanMau"], errors="coerce")
    reception_df = reception_df.sort_values(by="thoiGianNhanMau")

    st.dataframe(reception_df, use_container_width=True)

    selected_pid = st.selectbox("Select a PID to mark as received:", reception_df["PID"].tolist())
    if st.button("Mark as Received"):
        vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
        timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
        user_info = st.session_state["user_info"]
        append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, [[selected_pid, timestamp, user_info["tenNhanVien"]]])
        st.success(f"PID {selected_pid} marked as received.")

            
def display_registration_tab():
    """Displays the New Registration tab."""
    st.title("Register New PID")
    pid = st.text_input("Enter PID:")

    if st.button("Register PID"):
        user_info = st.session_state.get("user_info", {})
        if pid:
            try:
                register_pid(pid, user_info.get("tenNhanVien", "Unknown"))
                st.success(f"PID {pid} registered successfully.")
            except Exception as e:
                st.error(f"Error registering PID: {e}")
        else:
            st.error("Please enter a PID.")

# Main App Logic
if not st.session_state.get('is_logged_in', False):
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
        user = nhanvien_df[(nhanvien_df['taiKhoan'] == username) & (nhanvien_df['matKhau'] == password)]
        if not user.empty:
            user_info = user.iloc[0].to_dict()
            st.session_state['is_logged_in'] = True
            st.session_state['user_info'] = user_info
            st.success(f"Welcome, {user_info['tenNhanVien']}!")
        else:
            st.error("Invalid username or password.")
else:
    user_info = st.session_state['user_info']
    st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']}")

    # Sidebar Navigation
    selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception"])

    if selected_tab == "Register New PID":
        display_registration_tab()
    elif selected_tab == "Reception":
        display_reception_tab()

    # Logout Button
    if st.sidebar.button("Logout"):
        st.session_state.clear()
