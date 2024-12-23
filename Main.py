import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
import time

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
        active_tables = login_log_df[login_log_df['thoiGianLogout'] == ""]["table"].tolist()
        available_tables = [table for table in all_tables if table not in active_tables]
    else:
        available_tables = all_tables  # All tables are available if no log exists

    # Table selection dropdown
    selected_table = st.selectbox("Select a table to log in:", available_tables)

    # User credentials input
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        # Load the NhanVien sheet data
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)

        # Check for proper columns in the sheet
        if 'taiKhoan' not in nhanvien_df.columns or 'matKhau' not in nhanvien_df.columns:
            st.error("The required columns 'taiKhoan' and 'matKhau' are missing in the NhanVien sheet.")
            return

        # Trim whitespaces from column names and data
        nhanvien_df.columns = nhanvien_df.columns.str.strip()
        nhanvien_df = nhanvien_df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

        # Perform login validation
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
                [[selected_table, user_info['tenNhanVien'], login_time, ""]]
            )

            st.success(f"Welcome, {user_info['tenNhanVien']}! You are logged in at table {selected_table}.")
        else:
            st.error("Invalid username or password.")



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
    """Displays the Reception tab for managing PIDs."""
    st.write("### Reception Management")

    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau", "table"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    user_name = st.session_state["user_info"]["tenNhanVien"]
    reception_df = reception_df.replace("", None)

    filtered_df = reception_df[
        (reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLayMau"] == user_name)
    ]
    filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

    st.write("### Patients for Current Receptionist")
    st.dataframe(filtered_df, use_container_width=True)

    if not filtered_df.empty:
        selectable_pids = filtered_df[filtered_df["thoiGianLayMau"].isna()]["PID"].tolist()
        selected_pid = st.selectbox("Select a PID to mark as received:", selectable_pids)
        if st.button("Mark as Received"):
            reception_df.loc[reception_df["PID"] == selected_pid, "thoiGianLayMau"] = datetime.now(
                pytz.timezone("Asia/Ho_Chi_Minh")
            ).strftime("%Y-%m-%d %H:%M:%S")
            reception_df.loc[reception_df["PID"] == selected_pid, "nguoiLayMau"] = user_name
            reception_df.loc[reception_df["PID"] == selected_pid, "table"] = st.session_state['selected_table']

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

def display_table_tab():
    """Displays the Table tab for managing PIDs without thoiGianLayMau."""
    st.title("Table Overview")
    
    # Create a placeholder for the table content
    placeholder = st.empty()
    refresh_interval = 30  # seconds

    # Fetch and display data inside a loop
    while True:
        with placeholder.container():
            # Fetch data from the NhanMau sheet
            nhanmau_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
            if nhanmau_df.empty:
                st.write("No pending PIDs.")
            else:
                # Ensure required columns exist
                required_columns = {"PID", "tenBenhNhan", "thoiGianLayMau", "table"}
                if not required_columns.issubset(nhanmau_df.columns):
                    st.error(f"The sheet must contain these columns: {required_columns}")
                else:
                    # Normalize null values
                    nhanmau_df = nhanmau_df.replace("", None)  # Convert blank strings to None

                    # Filter rows where 'thoiGianLayMau' is empty
                    filtered_df = nhanmau_df[nhanmau_df["thoiGianLayMau"].isna()]

                    # Rename columns for display
                    filtered_df = filtered_df.rename(columns={
                        "PID": "PID",
                        "tenBenhNhan": "Họ tên",
                        "table": "Bàn"
                    })

                    # Select only relevant columns for display
                    filtered_df = filtered_df[["PID", "Họ tên", "Bàn"]]

                    # Display the table
                    if not filtered_df.empty:
                        st.write("### Pending PIDs")
                        st.dataframe(filtered_df, use_container_width=True)
                    else:
                        st.write("No pending PIDs.")

            # Countdown timer
            for i in range(refresh_interval, 0, -1):
                st.write(f"Refreshing in {i} seconds...", key=f"countdown_{i}")
                time.sleep(1)

        # Clear all output within the placeholder before the next refresh
        placeholder.empty()



        
# Main App Logic with an additional tab
if not st.session_state.get('is_logged_in', False):
    display_login_page()
else:
    user_info = st.session_state['user_info']
    st.sidebar.header(f"Logged in as: {user_info['tenNhanVien']} (Table {st.session_state['selected_table']})")

    selected_tab = st.sidebar.radio("Navigate", ["Register New PID", "Reception", "Table Overview"])
    
    if selected_tab == "Register New PID":
        display_registration_tab()
    elif selected_tab == "Reception":
        display_reception_tab()
    elif selected_tab == "Table Overview":
        display_table_tab()

    # Logout Button Handling
    if st.sidebar.button("Logout"):
        # Update `thoiGianLogout` in the Login Log Sheet
        vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
        logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

        # Fetch current login log data
        login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)

        if not login_log_df.empty:
            # Find the row corresponding to the current user's login
            login_log_df = login_log_df.replace("", None)
            user_row_index = login_log_df[login_log_df["tenNhanVien"] == user_info["tenNhanVien"]].index.tolist()

            if user_row_index:
                user_row_index = user_row_index[0]  # Get the first matching index
                login_log_df.loc[user_row_index, "thoiGianLogout"] = logout_time

                # Push updated data back to Google Sheets
                updated_values = [login_log_df.columns.tolist()] + login_log_df.fillna("").values.tolist()
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=LOGIN_LOG_SHEET_ID,
                    range=LOGIN_LOG_SHEET_RANGE,
                    valueInputOption="USER_ENTERED",
                    body={"values": updated_values}
                ).execute()

        # Clear session state
        st.session_state.clear()

    # Handle browser/tab close event
    def handle_tab_close():
        # Check if user info exists in session
        if "user_info" in st.session_state:
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

            # Fetch current login log data
            login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)

            if not login_log_df.empty:
                # Find the row corresponding to the current user's login
                login_log_df = login_log_df.replace("", None)
                user_row_index = login_log_df[login_log_df["tenNhanVien"] == st.session_state["user_info"]["tenNhanVien"]].index.tolist()

                if user_row_index:
                    user_row_index = user_row_index[0]  # Get the first matching index
                    login_log_df.loc[user_row_index, "thoiGianLogout"] = logout_time

                    # Push updated data back to Google Sheets
                    updated_values = [login_log_df.columns.tolist()] + login_log_df.fillna("").values.tolist()
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=LOGIN_LOG_SHEET_ID,
                        range=LOGIN_LOG_SHEET_RANGE,
                        valueInputOption="USER_ENTERED",
                        body={"values": updated_values}
                    ).execute()

    # Call `handle_tab_close()` when the app is closed or refreshed
    st.session_state["on_close_callback"] = handle_tab_close

