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
    
    # Normalize rows to match the number of headers
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
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0].get("hoten", "").strip()
            else:
                st.error("No patient data found in the response.")
        else:
            st.error(f"Failed to fetch patient data. HTTP Status: {response.status_code}")
    except requests.RequestException as e:
        st.error(f"Error fetching data from API: {e}")
    return None


def register_pid_with_name(pid, user_name):
    """Registers a new PID and fetches the patient name."""
    patient_name = fetch_patient_name(pid)
    if not patient_name:
        st.error("Failed to fetch patient name. Registration aborted.")
        return False
    
    # Current timestamp
    timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
    
    # Append data to Google Sheets
    data = [[pid, patient_name, timestamp, user_name, "", "", st.session_state["assigned_table"]]]
    append_to_sheet(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE, data)
    return True


def display_registration_tab():
    """Displays the New Registration tab."""
    st.title("Register New PID")
    pid = st.text_input("Enter PID:")
    if st.button("Register PID"):
        user_info = st.session_state.get("user_info", {})
        if pid:
            success = register_pid_with_name(pid, user_info.get("tenNhanVien"))
            if success:
                st.success(f"PID {pid} registered successfully.")
            else:
                st.error("Failed to register the PID.")

    # Display patients with `thoiGianLayMau` empty
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if not reception_df.empty:
        reception_df = reception_df.replace("", None)
        filtered_df = reception_df[reception_df["thoiGianLayMau"].isna()]
        if not filtered_df.empty:
            st.write("### Registered Patients")
            st.dataframe(filtered_df[["PID", "tenBenhNhan", "thoiGianNhanMau"]], use_container_width=True)


def display_reception_tab():
    """Displays the Reception tab."""
    st.title("Reception")
    user_info = st.session_state.get("user_info", {})
    user_name = user_info.get("tenNhanVien")
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

    if not reception_df.empty:
        reception_df = reception_df.replace("", None)
        filtered_df = reception_df[
            reception_df["thoiGianLayMau"].isna() | (reception_df["nguoiLayMau"] == user_name)
        ]
        if not filtered_df.empty:
            st.write("### Patients Available for Reception")
            st.dataframe(filtered_df[["PID", "tenBenhNhan", "thoiGianNhanMau"]], use_container_width=True)

            # Select PID
            pid_to_receive = st.selectbox("Select PID to mark as received:", filtered_df["PID"].tolist())
            if st.button("Mark as Received"):
                timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
                reception_df.loc[reception_df["PID"] == pid_to_receive, "thoiGianLayMau"] = timestamp
                reception_df.loc[reception_df["PID"] == pid_to_receive, "nguoiLayMau"] = user_name
                reception_df.loc[reception_df["PID"] == pid_to_receive, "table"] = st.session_state["assigned_table"]

                # Push updated data
                updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=RECEPTION_SHEET_ID,
                    range=RECEPTION_SHEET_RANGE,
                    valueInputOption="USER_ENTERED",
                    body={"values": updated_values}
                ).execute()
                st.success(f"PID {pid_to_receive} marked as received.")
        else:
            st.write("No patients available for reception.")


# Main App
if not st.session_state.get("is_logged_in", False):
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    assigned_table = st.selectbox("Select Table:", range(1, 6))
    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
        user = nhanvien_df[(nhanvien_df["taiKhoan"] == username) & (nhanvien_df["matKhau"] == password)]
        if not user.empty:
            user_info = user.iloc[0].to_dict()
            st.session_state["is_logged_in"] = True
            st.session_state["user_info"] = user_info
            st.session_state["assigned_table"] = assigned_table
            st.success(f"Welcome, {user_info['tenNhanVien']}!")
else:
    st.sidebar.header(f"Logged in as: {st.session_state['user_info']['tenNhanVien']}")
    selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception"])
    if selected_tab == "Register New PID":
        display_registration_tab()
    elif selected_tab == "Reception":
        display_reception_tab()
    if st.sidebar.button("Logout"):
        st.session_state.clear()
