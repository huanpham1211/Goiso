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
        st.warning(f"No data found in range: {range_name}")
        return pd.DataFrame()  # Return an empty DataFrame if no data is found
    
    headers = values[0] if len(values) > 0 else []
    rows = values[1:] if len(values) > 1 else []
    
    # Ensure all rows match the number of headers
    normalized_rows = [row + [''] * (len(headers) - len(row)) for row in rows]
    
    if not rows:
        st.warning("No data rows found in the sheet.")
        return pd.DataFrame(columns=headers)  # Return DataFrame with just headers
    
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

def mark_pid_as_received(pid, ten_lay_mau):
    """Marks a PID as received with sample collection details."""
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    
    if reception_df.empty:
        st.error("No data available to update.")
        return
    
    # Find the index of the row with the specified PID
    row_index = reception_df.index[reception_df["PID"] == pid].tolist()
    if not row_index:
        st.error(f"PID {pid} not found.")
        return
    
    row_index = row_index[0]  # Get the first matching row
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
    
    # Update the row with the collection details
    reception_df.loc[row_index, "thoiGianLayMau"] = timestamp
    reception_df.loc[row_index, "nguoiLayMau"] = ten_lay_mau
    
    # Push the updated data back to Google Sheets
    updated_values = [reception_df.columns.tolist()] + reception_df.values.tolist()
    body = {'values': updated_values}
    sheets_service.spreadsheets().values().update(
        spreadsheetId=RECEPTION_SHEET_ID,
        range=RECEPTION_SHEET_RANGE,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return
    
    # Ensure DataFrame has expected columns
    required_columns = {"PID", "thoiGianNhanMau", "nguoiNhan", "thoiGianLayMau", "nguoiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return
    
    # Convert and sort timestamps
    reception_df["thoiGianNhanMau"] = pd.to_datetime(reception_df["thoiGianNhanMau"], errors="coerce")
    reception_df = reception_df.sort_values(by="thoiGianNhanMau")

    st.write("### Registered PIDs")
    st.dataframe(reception_df, use_container_width=True)

    # Mark PID as received
    selected_pid = st.selectbox("Select a PID to mark as received:", reception_df["PID"].tolist())
    if st.button("Mark as Received"):
        user_info = st.session_state["user_info"]
        mark_pid_as_received(selected_pid, user_info["tenNhanVien"])
        st.success(f"PID {selected_pid} marked as received.")

# Main App Logic
if not st.session_state.get('is_logged_in', False):
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
        user = nhanvien_df[
            (nhanvien_df['taiKhoan'] == username) & (nhanvien_df['matKhau'] == password)
        ]
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

    # Tabs
    tab1, tab2 = st.tabs(["Register New PID", "Reception"])
    
    # Register New PID Tab
    with tab1:
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

    # Reception Tab
    with tab2:
        display_reception_tab()

    # Logout Button
    if st.sidebar.button("Logout"):
        st.session_state['is_logged_in'] = False
        st.session_state['user_info'] = None
        st.experimental_rerun()

