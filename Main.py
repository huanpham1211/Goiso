import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import time

# Constants
NHANVIEN_SHEET_ID = '1kzfwjA0nVLFoW8T5jroLyR2lmtdZp8eaYH-_Pyb0nbk'
NHANVIEN_SHEET_RANGE = 'Sheet1'
RECEPTION_SHEET_ID = '1Y3uYVe_A7w00_AfywqprA7qolsf8CMOvgrUHV3hmB6E'
RECEPTION_SHEET_RANGE = 'Sheet1'

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


# Helper functions
def read_google_sheet(sheet_id, sheet_range):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
    values = result.get('values', [])
    return pd.DataFrame(values[1:], columns=values[0]) if values else pd.DataFrame()

def append_to_google_sheet(sheet_id, sheet_range, data):
    body = {"values": [data]}
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=sheet_range,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

def check_login(username, password):
    user = nhanvien_df[
        (nhanvien_df['taiKhoan'].astype(str) == str(username)) &
        (nhanvien_df['matKhau'].astype(str) == str(password))
    ]
    return user.iloc[0].to_dict() if not user.empty else None

# Load Data
nhanvien_df = read_google_sheet(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)

# Initialize session state
if 'logged_in_user' not in st.session_state:
    st.session_state.logged_in_user = None

# Login page
if st.session_state.logged_in_user is None:
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = check_login(username, password)
        if user:
            st.session_state.logged_in_user = user
            st.success("Login successful!")
            st.experimental_rerun()
        else:
            st.error("Invalid credentials")
else:
    user = st.session_state.logged_in_user
    st.sidebar.header(f"Welcome, {user['taiKhoan']}!")

    # Tabs
    tab1, tab2 = st.tabs(["New Registration", "Reception"])
    
    # New Registration Tab
    with tab1:
        st.header("New Registration")
        pid = st.text_input("Enter PID:")
        if st.button("Register PID"):
            if pid:
                now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                append_to_google_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, [pid, timestamp, user['maNVYT']])
                st.success(f"PID {pid} registered successfully.")
            else:
                st.error("Please enter a PID.")

    # Reception Tab
    with tab2:
        st.header("Reception")
        reception_df = read_google_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
        if not reception_df.empty:
            reception_df.columns = ["PID", "thoiGianNhanMau", "nguoiNhan"]
            reception_df.sort_values("thoiGianNhanMau", inplace=True)
            for _, row in reception_df.iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"PID: {row['PID']} - Received by: {row['nguoiNhan']}")
                with col2:
                    if st.button(f"Receive {row['PID']}"):
                        now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))
                        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                        append_to_google_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, [row['PID'], timestamp, user['maNVYT']])
                        st.success(f"PID {row['PID']} received.")
                        st.experimental_rerun()
        else:
            st.write("No PIDs available for reception.")

    # Logout Button
    if st.sidebar.button("Logout"):
        st.session_state.logged_in_user = None
        st.experimental_rerun()
