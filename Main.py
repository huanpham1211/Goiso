import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
import xml.etree.ElementTree as ET

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

def fetch_patient_name(pid):
    """Fetches the patient name from the API."""
    url = f"https://api.bvhungvuong.vn/api/dangkykham/?ip=&idbv=&id=&mabn={pid}&ngay="
    try:
        response = requests.get(url)

        if response.status_code == 200:
            try:
                # Parse the JSON response
                data = response.json()
                
                # Check if 'data' exists and contains entries
                if 'data' in data and len(data['data']) > 0:
                    patient_info = data['data'][0]
                    hoten = patient_info.get("hoten")
                    if hoten:
                        return hoten.strip()
                    else:
                        st.error("The response does not contain a valid 'hoten' field.")
                        return None
                else:
                    st.error("No patient data found in the response.")
                    return None
            except ValueError as e:
                st.error(f"Error parsing JSON response: {e}")
                st.write(f"API Response: {response.content.decode('utf-8')}")
                return None
        else:
            st.error(f"Failed to fetch patient data. HTTP Status: {response.status_code}")
            st.write(f"API Response: {response.content.decode('utf-8')}")
            return None
    except requests.RequestException as e:
        st.error(f"Error fetching data from API: {e}")
        return None



def register_pid_with_name(pid, ten_nhan_vien):
    """Registers a new PID and fetches the patient name."""
    # Fetch the patient's name
    patient_name = fetch_patient_name(pid)
    if not patient_name:
        st.error("Failed to fetch patient name. Registration aborted.")
        return False  # Abort if name couldn't be fetched

    # Get the current timestamp
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    timestamp = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

    # Data to append to the Google Sheet
    data = [[pid, patient_name, timestamp, ten_nhan_vien, "", ""]]  # Include patient_name in tenBenhNhan
    append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, data)

    st.session_state['last_registered_pid'] = pid  # Store the last registered PID for updates
    return True

def display_registration_tab():
    """Displays the New Registration tab."""
    st.title("Register New PID")
    
    # Input for new PID
    pid = st.text_input("Enter PID:")
    
    # Register New PID
    if st.button("Register PID"):
        user_info = st.session_state.get("user_info", {})
        if pid:
            try:
                success = register_pid_with_name(pid, user_info.get("tenNhanVien", "Unknown"))
                if success:
                    st.success(f"PID {pid} registered successfully.")
                else:
                    st.error("Failed to register the PID.")
            except Exception as e:
                st.error(f"Error registering PID: {e}")
        else:
            st.error("Please enter a PID.")

    # Fetch data from the sheet
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    # Normalize null values
    reception_df = reception_df.replace("", None)  # Convert blank strings to None

    # Filter rows where 'thoiGianLayMau' or 'nguoiLayMau' is empty
    filtered_df = reception_df[
        reception_df["thoiGianLayMau"].isna() & reception_df["nguoiLayMau"].isna()
    ]

    # Sort by 'thoiGianNhanMau' in ascending order
    filtered_df["thoiGianNhanMau"] = pd.to_datetime(filtered_df["thoiGianNhanMau"], errors="coerce")
    filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

    # Rename columns for display
    filtered_df = filtered_df.rename(columns={
        "PID": "PID",
        "tenBenhNhan": "Họ tên",
        "thoiGianNhanMau": "Thời gian nhận mẫu",
    })

    # Select only relevant columns for display
    filtered_df = filtered_df[["PID", "Họ tên", "Thời gian nhận mẫu"]]

    # Display the table
    if not filtered_df.empty:
        st.write("### Registered Patients")
        st.dataframe(filtered_df, use_container_width=True)
    else:
        st.write("No patients pending collection.")


def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.write("### Reception Management")

    # Fetch data from the sheet
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    # Normalize null values
    reception_df = reception_df.replace("", None)  # Convert blank strings to None

    # Current logged-in user's name
    user_name = st.session_state["user_info"]["tenNhanVien"]

    # Filter rows where 'thoiGianLayMau' is empty or 'nguoiLayMau' matches the logged-in user
    filtered_df = reception_df[
        reception_df["thoiGianLayMau"].isna() | (reception_df["nguoiLayMau"] == user_name)
    ]

    # Sort by 'thoiGianNhanMau' in ascending order
    filtered_df["thoiGianNhanMau"] = pd.to_datetime(filtered_df["thoiGianNhanMau"], errors="coerce")
    filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

    # Rename columns for display
    filtered_df = filtered_df.rename(columns={
        "PID": "PID",
        "tenBenhNhan": "Họ tên",
        "thoiGianNhanMau": "Thời gian nhận mẫu",
        "thoiGianLayMau": "Thời gian lấy máu",
        "nguoiLayMau": "Người lấy máu",
    })

    # Select only relevant columns for display
    display_df = filtered_df[["PID", "Họ tên", "Thời gian nhận mẫu", "Thời gian lấy máu", "Người lấy máu"]]

    # Display the table
    if not display_df.empty:
        st.write("### Patients for Current Receptionist")
        st.dataframe(display_df, use_container_width=True)
    else:
        st.write("No patients pending or assigned to you.")

    # Filter for PID selection (only show rows with empty 'Thời gian lấy máu')
    selectable_pids = filtered_df[filtered_df["Thời gian lấy máu"].isna()]["PID"].tolist()

    # Mark as Received functionality
    if selectable_pids:
        selected_pid = st.selectbox("Select a PID to mark as received:", selectable_pids)
        if st.button("Mark as Received"):
            # Update thoiGianLayMau and nguoiLayMau for the selected PID
            now = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            reception_df.loc[reception_df["PID"] == selected_pid, "thoiGianLayMau"] = now
            reception_df.loc[reception_df["PID"] == selected_pid, "nguoiLayMau"] = user_name

            # Push updated data back to Google Sheets
            updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
            body = {"values": updated_values}
            sheets_service.spreadsheets().values().update(
                spreadsheetId=RECEPTION_SHEET_ID,
                range=RECEPTION_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()

            st.success(f"PID {selected_pid} marked as received.")

            # Reload the filtered data dynamically
            # Refetch updated data
            refreshed_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
            refreshed_df = refreshed_df[
                refreshed_df["thoiGianLayMau"].isna() | (refreshed_df["nguoiLayMau"] == user_name)
            ]
            refreshed_df["thoiGianNhanMau"] = pd.to_datetime(refreshed_df["thoiGianNhanMau"], errors="coerce")
            refreshed_df = refreshed_df.sort_values(by="thoiGianNhanMau")

            # Update the displayed table
            refreshed_df = refreshed_df.rename(columns={
                "PID": "PID",
                "tenBenhNhan": "Họ tên",
                "thoiGianNhanMau": "Thời gian nhận mẫu",
                "thoiGianLayMau": "Thời gian lấy máu",
                "nguoiLayMau": "Người lấy máu",
            })
            refreshed_df = refreshed_df[["PID", "Họ tên", "Thời gian nhận mẫu", "Thời gian lấy máu", "Người lấy máu"]]

            # Display refreshed data
            if not refreshed_df.empty:
                st.write("### Updated Patients for Current Receptionist")
                st.dataframe(refreshed_df, use_container_width=True)
            else:
                st.write("No patients pending or assigned to you.")
    else:
        st.write("No selectable PIDs available for marking as received.")




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
