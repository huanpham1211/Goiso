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
    SELECT PID, tenBenhNhan, thoiGianNhanMau, thoiGianLayMau, nguoiLay, banGoiSo, ketThucLayMau 
    FROM [QualityControl].[dbo].[LayMauXetNghiem];
    """
    reception_df = pd.read_sql(query, conn)

    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLay", "banGoiSo", "ketThucLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The table must contain these columns: {required_columns}")
        return

    user_info = st.session_state.get("user_info", {})
    user_name = user_info.get("tenNhanVien")
    ma_nvyt = user_info.get("maNVYT")
    selected_table = st.session_state.get("selected_table", None)

    # Normalize null values
    reception_df = reception_df.replace("", None)

    # Filter rows based on the following criteria:
    filtered_df = reception_df[
        ((reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLay"] == ma_nvyt)) &
        (reception_df["ketThucLayMau"] != "1")
    ]

    # Sort the filtered rows:
    # 1. By `thoiGianNhanMau` in ascending order
    filtered_df = filtered_df.sort_values(by=["thoiGianNhanMau"], ascending=True)

    if not filtered_df.empty:
        for idx, row in filtered_df.iterrows():
            pid = row["PID"]
            ten_benh_nhan = row["tenBenhNhan"]
            col1, col2, col3 = st.columns([4, 4, 2])
            col1.write(f"**PID:** {pid}")
            col2.write(f"**Họ tên:** {ten_benh_nhan}")

            # Generate a unique key for each button by including `pid` and `idx`
            button_key = f"receive_{pid}_{idx}"
            if col3.button("Receive", key=button_key):
                # Update the LayMauXetNghiem table with current time and user information
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                update_query = """
                UPDATE [QualityControl].[dbo].[LayMauXetNghiem]
                SET thoiGianLayMau = ?, nguoiLay = ?, banGoiSo = ?
                WHERE PID = ?;
                """
                cursor.execute(update_query, current_time, ma_nvyt, selected_table, pid)
                conn.commit()

                st.success(f"Bắt đầu lấy máu cho PID {pid}.")
    else:
        st.write("Chưa có bệnh nhân.")

    # Close the database connection
    conn.close()




def display_blood_draw_completion_tab():
    """Handles the Blood Draw Completion tab."""
    if "current_pid" not in st.session_state or "current_ten_benh_nhan" not in st.session_state:
        st.write("Chưa có bệnh nhân cần lấy máu.")
        return

    pid = st.session_state["current_pid"]
    ten_benh_nhan = st.session_state["current_ten_benh_nhan"]

    st.write("### Blood Draw Completion")
    st.write(f"**PID:** {pid}")
    st.write(f"**Họ tên:** {ten_benh_nhan}")

    if st.button("Blood draw completed"):
        # Fetch the sheet data
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

        # Update the column `ketThucLayMau` for the selected PID
        if "ketThucLayMau" not in reception_df.columns:
            st.error("The sheet must contain the column 'ketThucLayMau'.")
            return

        reception_df = reception_df.replace("", None)  # Normalize empty strings
        reception_df.loc[reception_df["PID"] == pid, "ketThucLayMau"] = "1"

        # Prepare the updated values
        updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
        sheets_service.spreadsheets().values().update(
            spreadsheetId=RECEPTION_SHEET_ID,
            range=RECEPTION_SHEET_RANGE,
            valueInputOption="USER_ENTERED",
            body={"values": updated_values}
        ).execute()

        # Clear session state for current PID
        del st.session_state["current_pid"]
        del st.session_state["current_ten_benh_nhan"]

        # Notify user and redirect back to the Reception tab
        st.success("Lấy máu hoàn tất. Quay lại thẻ 'Gọi bệnh nhân'.")



        
if not st.session_state.get('is_logged_in', False):
    display_login_page()
else:
    user_info = st.session_state['user_info']
    selected_table = st.session_state['selected_table']

    # Sidebar header with user information
    st.sidebar.header(f"{user_info['tenNhanVien']} (Bàn {selected_table})")

    # Restrict tabs to tables 1–5
    if selected_table in ["1", "2", "3", "4", "5"]:
        tabs = ["Gọi bệnh nhân", "Hoàn tất lấy máu"]

        selected_tab = st.sidebar.radio("Navigate", tabs)

        # Render the appropriate tab
        if selected_tab == "Gọi bệnh nhân":
            display_reception_tab()
        elif selected_tab == "Hoàn tất lấy máu":
            display_blood_draw_completion_tab()
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


