import streamlit as st
import pandas as pd
from datetime import datetime
import json
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
import time
from datetime import datetime, timedelta
import pyodbc


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

    # Allowed table options (1–5)
    all_tables = [str(i) for i in range(1, 6)]

    # Generate dropdown options directly from the table list
    dropdown_options = all_tables

    # Table selection dropdown
    selected_table = st.selectbox("Select a table to log in:", dropdown_options)

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

            st.success(f"Xin chào, {user_info['tenNhanVien']}! Đã đăng nhập vào bàn lấy máu số {selected_table}.")
        else:
            st.error("Sai thông tin User hoặc Password.")



def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.title("Lấy máu")

    # Initialize session state for refresh if not already set
    if "refresh_data" not in st.session_state:
        st.session_state["refresh_data"] = True

    # Refresh Button
    if st.button("Refresh"):
        st.session_state["refresh_data"] = True  # Set the refresh flag to True

    # Fetch data from the database only if refresh flag is set
    if st.session_state["refresh_data"]:
        # Database connection setup
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=10.17.4.38,1433;"
            "DATABASE=QualityControl;"
            "UID=xetnghiemhv;"
            "PWD=Huan@123"
        )
        cursor = conn.cursor()

        # Fetch data from the LayMauXetNghiem table
        query = """
        SELECT maBenhNhan, tenBenhNhan, thoiGianNhanMau, thoiGianLayMau, nguoiLay, banGoiSo, trangThaiLayMau 
        FROM [QualityControl].[dbo].[LayMauXetNghiem]
        WHERE trangThaiLayMau IS NULL;
        """
        reception_df = pd.read_sql(query, conn)
        conn.close()

        # Store fetched data in session state
        st.session_state["reception_data"] = reception_df
        st.session_state["refresh_data"] = False  # Reset the refresh flag

    # Load the data from session state
    reception_df = st.session_state.get("reception_data", pd.DataFrame())

    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"maBenhNhan", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLay", "banGoiSo", "trangThaiLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The table must contain these columns: {required_columns}")
        return

    # Normalize null values
    reception_df = reception_df.replace("", None)

    user_info = st.session_state.get("user_info", {})
    user_name = user_info.get("tenNhanVien")
    ma_nvyt = user_info.get("maNVYT")
    selected_table = st.session_state.get("selected_table", None)

    # Sort the rows by `thoiGianNhanMau` in ascending order
    reception_df = reception_df.sort_values(by=["thoiGianNhanMau"], ascending=True)

    # Display filtered rows
    for idx, row in reception_df.iterrows():
        pid = row["maBenhNhan"]
        ten_benh_nhan = row["tenBenhNhan"]
        col1, col2, col3, col4 = st.columns([3, 4, 2, 2])

        col1.write(f"**PID:** {pid}")
        col2.write(f"**Họ tên:** {ten_benh_nhan}")

        # "Receive" button
        if col3.button("Receive", key=f"receive_{pid}_{idx}"):
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = pyodbc.connect(
                "DRIVER={ODBC Driver 17 for SQL Server};"
                "SERVER=10.17.4.38,1433;"
                "DATABASE=QualityControl;"
                "UID=xetnghiemhv;"
                "PWD=Huan@123"
            )
            cursor = conn.cursor()
            update_query = """
            UPDATE [QualityControl].[dbo].[LayMauXetNghiem]
            SET thoiGianLayMau = ?, nguoiLay = ?, banGoiSo = ?
            WHERE maBenhNhan = ?;
            """
            cursor.execute(update_query, current_time, ma_nvyt, selected_table, pid)
            conn.commit()
            conn.close()
            st.success(f"Bắt đầu lấy máu cho PID {pid}.")
            st.session_state["refresh_data"] = True  # Trigger data refresh

        # "Blood draw completed" button
        if col4.button("Blood draw completed", key=f"completed_{pid}_{idx}"):
            conn = pyodbc.connect(
                "DRIVER={ODBC Driver 17 for SQL Server};"
                "SERVER=10.17.4.38,1433;"
                "DATABASE=QualityControl;"
                "UID=xetnghiemhv;"
                "PWD=Huan@123"
            )
            cursor = conn.cursor()
            update_query = """
            UPDATE [QualityControl].[dbo].[LayMauXetNghiem]
            SET trangThaiLayMau = '1'
            WHERE maBenhNhan = ?;
            """
            cursor.execute(update_query, pid)
            conn.commit()
            conn.close()
            st.success(f"Hoàn tất lấy máu cho PID {pid}.")
            st.session_state["refresh_data"] = True  # Trigger data refresh




if not st.session_state.get('is_logged_in', False):
    display_login_page()
else:
    user_info = st.session_state['user_info']
    selected_table = st.session_state['selected_table']

    # Sidebar header with user information
    st.sidebar.header(f"{user_info['tenNhanVien']} (Bàn {selected_table})")

    # Restrict access to tables 1–5
    if selected_table in ["1", "2", "3", "4", "5"]:
        # Display the Reception tab directly
        display_reception_tab()
    else:
        st.error("Only tables 1–5 are allowed.")

    # Logout Button Handling
    if st.sidebar.button("Logout"):
        # Update `thoiGianLogout` in the database or sheet (adjust as needed)
        vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
        logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

        # Fetch current login log data
        login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)

        if not login_log_df.empty:
            # Find the row corresponding to the current user's login
            login_log_df = login_log_df.replace("", None)
            user_row_index = login_log_df[
                (login_log_df["tenNhanVien"] == user_info["tenNhanVien"]) &
                (login_log_df["table"] == selected_table)
            ].index.tolist()

            if user_row_index:
                user_row_index = user_row_index[0]  # Get the first matching index
                login_log_df.at[user_row_index, "thoiGianLogout"] = logout_time

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
        st.success("You have been logged out.")



