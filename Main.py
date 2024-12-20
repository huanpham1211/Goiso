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

# Function to fetch data from a Google Sheet
def fetch_sheet_data(sheet_id, range_name):
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()
    values = result.get('values', [])
    return pd.DataFrame(values[1:], columns=values[0]) if values else pd.DataFrame()

# Function to append data to a Google Sheet
def append_to_sheet(sheet_id, range_name, values):
    body = {'values': values}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

# Load Google Sheets data into Streamlit session state
if 'nhanvien_df' not in st.session_state:
    st.session_state['nhanvien_df'] = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)

# Helper function to check login
def check_login(username, password):
    nhanvien_df = st.session_state['nhanvien_df']
    user = nhanvien_df[
        (nhanvien_df['taiKhoan'].astype(str) == str(username)) &
        (nhanvien_df['matKhau'].astype(str) == str(password))
    ]
    return user.iloc[0].to_dict() if not user.empty else None

# Helper function to append new registration data
def register_pid(pid, ten_nhan_vien):
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = [[pid, timestamp, ten_nhan_vien]]
    append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, data)

# Login Page
if not st.session_state.get('is_logged_in', False):
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        user = check_login(username, password)
        if user:
            st.session_state['is_logged_in'] = True
            st.session_state['user_info'] = user
            st.success(f"Welcome, {user['tenNhanVien']}!")
        else:
            st.error("Invalid username or password.")
else:
    user_info = st.session_state['user_info']
    st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']}")

    # PID Registration Page
    st.title("Register New PID")
    pid = st.text_input("Enter PID:")
    
    if st.button("Register PID"):
        if pid:
            try:
                register_pid(pid, user_info['tenNhanVien'])
                st.success(f"PID {pid} registered successfully.")
            except Exception as e:
                st.error(f"Error registering PID: {e}")
        else:
            st.error("Please enter a PID.")

    # Logout Button
    if st.sidebar.button("Logout"):
        st.session_state['is_logged_in'] = False
        st.session_state['user_info'] = None
        st.experimental_rerun()
