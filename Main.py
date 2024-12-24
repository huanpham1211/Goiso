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

    # All table options (1–6)
    all_tables = [str(i) for i in range(1, 7)]

    # Create display mapping for the dropdown
    table_display_mapping = {table: table for table in all_tables[:-1]}
    table_display_mapping["6"] = "Nhận mẫu"

    # Reverse mapping for internal use
    display_to_internal_mapping = {v: k for k, v in table_display_mapping.items()}

    # Generate dropdown options using the display mapping
    dropdown_options = [table_display_mapping[table] for table in all_tables]

    # Table selection dropdown
    selected_display_table = st.selectbox("Select a table to log in:", dropdown_options)
    selected_table = display_to_internal_mapping[selected_display_table]

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

            # Custom message for "Nhận mẫu" table
            if selected_table == "6":
                st.success(f"Xin chào, {user_info['tenNhanVien']}! Đã đăng nhập vào 'Nhận mẫu'.")
            else:
                st.success(f"Xin chào, {user_info['tenNhanVien']}! Đã đăng nhập vào bàn lấy máu số {selected_table}.")
        else:
            st.error("Sai thông tin User hoặc Password.")





def display_registration_tab():
    """Displays the Registration tab."""
    st.title("Đăng ký PID mới")

    # Initialize session state for 'pid' if not already done
    if "pid" not in st.session_state:
        st.session_state["pid"] = ""

    # Create a text input field linked to session state
    pid = st.text_input("Nhập PID:", value=st.session_state["pid"], key="pid")

    col1, col2 = st.columns(2)

    if col1.button("Đăng ký"):
        user_info = st.session_state["user_info"]
        patient_name = fetch_patient_name(pid)
        if patient_name:
            timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            # Append data to the sheet without the selected table column
            append_to_sheet(
                RECEPTION_SHEET_ID,
                RECEPTION_SHEET_RANGE,
                [[pid, patient_name, timestamp, user_info["tenNhanVien"], "", ""]]
            )
            st.success(f"PID {pid} đăng ký thành công cho {patient_name}.")
            # Clear the input field
            st.session_state["pid"] = ""
        else:
            st.error("Không thể lấy thông tin bệnh nhân.")

    if col2.button("Ưu tiên"):
        user_info = st.session_state["user_info"]
        patient_name = fetch_patient_name(pid)
        if patient_name:
            timestamp = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            # Append data to the sheet with is_priority set to "1"
            append_to_sheet(
                RECEPTION_SHEET_ID,
                RECEPTION_SHEET_RANGE,
                [[pid, patient_name, timestamp, user_info["tenNhanVien"], "", "1"]]
            )
            st.success(f"PID {pid} đăng ký thành công và được đánh dấu ưu tiên cho {patient_name}.")
            # Clear the input field
            st.session_state["pid"] = ""
        else:
            st.error("Không thể lấy thông tin bệnh nhân.")





def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.title("Lấy máu")

    # Add a refresh button to reload the data
    if st.button("Refresh"):
        # Fetch the latest data without rerun
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    else:
        # Fetch the data at the beginning
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau", "table", "ketThucLayMau"}
    if not required_columns.issubset(reception_df.columns):
        st.error(f"The sheet must contain these columns: {required_columns}")
        return

    user_name = st.session_state["user_info"]["tenNhanVien"]
    selected_table = st.session_state.get("selected_table", None)
    reception_df = reception_df.replace("", None)

    # Add a new column to mark duplicates
    reception_df["is_duplicate"] = reception_df.duplicated(subset=["PID"], keep=False)

    # Filter rows based on the following criteria:
    # - Non-duplicates can be seen by all tables
    # - Duplicates can only be seen by Table 4 or Table 5 users
    if selected_table in ["4", "5"]:
        filtered_df = reception_df[
            ((reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLayMau"] == user_name)) &
            (reception_df["ketThucLayMau"] != "1")
        ]
    else:
        filtered_df = reception_df[
            (((reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLayMau"] == user_name)) &
             (reception_df["is_duplicate"] == False)) &
            (reception_df["ketThucLayMau"] != "1")
        ]

    # Sort the filtered rows:
    # 1. Duplicates first (`is_duplicate=True`)
    # 2. By `thoiGianNhanMau` in ascending order
    filtered_df = filtered_df.sort_values(by=["is_duplicate", "thoiGianNhanMau"], ascending=[False, True])

    # Display only relevant actions without showing the entire dataframe
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
                # Fill in the `NhanMau` sheet with current data
                vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
                current_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

                reception_df.loc[reception_df["PID"] == pid, "thoiGianLayMau"] = current_time
                reception_df.loc[reception_df["PID"] == pid, "nguoiLayMau"] = user_name
                reception_df.loc[reception_df["PID"] == pid, "table"] = selected_table

                # Convert DataFrame to a JSON-serializable format
                json_ready_df = reception_df.fillna("").astype(str)

                # Prepare the updated values
                updated_values = [json_ready_df.columns.tolist()] + json_ready_df.values.tolist()
                try:
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=RECEPTION_SHEET_ID,
                        range=RECEPTION_SHEET_RANGE,
                        valueInputOption="USER_ENTERED",
                        body={"values": updated_values}
                    ).execute()
                except Exception as e:
                    st.error(f"Failed to update Google Sheets: {e}")
                    return

                # Set session variables for Blood Draw Completion
                st.session_state["current_pid"] = pid
                st.session_state["current_ten_benh_nhan"] = ten_benh_nhan

                st.success(f"Bắt đầu lấy máu cho PID {pid}. Bấm vào thẻ 'Hoàn tất lấy máu' để tiếp tục.")
    else:
        st.write("Chưa có bệnh nhân.")






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


def display_table_tab():
    """Displays the Table tab for managing PIDs."""
    
    # Create a placeholder for the table content
    placeholder = st.empty()

    def fetch_and_display_table():
        nhanmau_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)

        if nhanmau_df.empty:
            with placeholder.container():
                st.write("Chưa có số thứ tự tiếp theo.")
            return

        # Ensure required columns exist
        required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "table", "ketThucLayMau"}
        if not required_columns.issubset(nhanmau_df.columns):
            with placeholder.container():
                st.error(f"The sheet must contain these columns: {required_columns}")
            return

        # Normalize null values
        nhanmau_df = nhanmau_df.replace("", None)
        nhanmau_df = nhanmau_df.dropna(subset=["PID", "tenBenhNhan", "table"])

        # Filter rows where 'table' is not null and 'ketThucLayMau' is not "1"
        filtered_df = nhanmau_df[
            nhanmau_df["table"].notna() & (nhanmau_df["ketThucLayMau"] != "1")
        ]

        # Sort the filtered rows:
        # 1. Duplicates first (duplicated=True)
        # 2. By thoiGianNhanMau in ascending order
        filtered_df["is_duplicate"] = nhanmau_df.duplicated(subset=["PID"], keep=False)
        filtered_df = filtered_df.sort_values(by=["is_duplicate", "thoiGianNhanMau"], ascending=[False, True])

        # Display the table content dynamically using columns
        with placeholder.container():
            if not filtered_df.empty:
                st.write("### Thứ tự bàn lấy máu")
                for idx, row in filtered_df.iterrows():
                    pid = row["PID"]
                    ten_benh_nhan = row["tenBenhNhan"]
                    table = row["table"]

                    # Create columns for each row
                    col1, col2, col3 = st.columns([2, 4, 2])
                    col1.markdown(f"<h3><b></b> {pid}</h3>", unsafe_allow_html=True)
                    col2.markdown(f"<h3><b></b> {ten_benh_nhan}</h3>", unsafe_allow_html=True)
                    col3.markdown(f"<h3><b>Bàn:</b> {table}</h3>", unsafe_allow_html=True)
            else:
                st.write("Chưa có số thứ tự tiếp theo.")

    # Fetch and display the table every 15 seconds
    while True:
        fetch_and_display_table()
        time.sleep(15)







# Function to update logout time for previous sessions
def handle_unexpected_logout():
    """Updates thoiGianLogout for previous sessions if not already logged out."""
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

    # Fetch current login log data
    login_log_df = fetch_sheet_data(LOGIN_LOG_SHEET_ID, LOGIN_LOG_SHEET_RANGE)

    if not login_log_df.empty:
        # Find rows where thoiGianLogout is empty for the current user and table
        login_log_df = login_log_df.replace("", None)
        user_rows = login_log_df[
            (login_log_df["tenNhanVien"] == st.session_state["user_info"]["tenNhanVien"]) &
            (login_log_df["table"] == st.session_state["selected_table"]) &
            (login_log_df["thoiGianLogout"].isna())
        ]

        # Update thoiGianLogout for those rows
        if not user_rows.empty:
            for idx in user_rows.index:
                login_log_df.at[idx, "thoiGianLogout"] = logout_time

            # Push updated data back to Google Sheets
            updated_values = [login_log_df.columns.tolist()] + login_log_df.fillna("").values.tolist()
            sheets_service.spreadsheets().values().update(
                spreadsheetId=LOGIN_LOG_SHEET_ID,
                range=LOGIN_LOG_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                body={"values": updated_values}
            ).execute()

        
# Main App Logic with restricted access for table 6 ("Nhận mẫu") and tables 1–5
if not st.session_state.get('is_logged_in', False):
    display_login_page()
else:
    user_info = st.session_state['user_info']
    selected_table = st.session_state['selected_table']
    st.sidebar.header(f"{user_info['tenNhanVien']} (Bàn {selected_table})")

    # Restrict tabs based on table type
    if selected_table == "6":  # "Nhận mẫu"
        tabs = ["Đăng ký mới PID", "Bảng gọi số"]
    else:  # Tables 1–5
        tabs = ["Gọi bệnh nhân", "Hoàn tất lấy máu"]

    selected_tab = st.sidebar.radio("Navigate", tabs)

    # Render the appropriate tab
    if selected_tab == "Đăng ký mới PID" and selected_table == "6":  # Only for table 6
        display_registration_tab()
    elif selected_tab == "Bảng gọi số" and selected_table == "6":  # Only for table 6
        display_table_tab()
    elif selected_tab == "Gọi bệnh nhân" and selected_table != "6":  # Only for tables 1–5
        display_reception_tab()
    elif selected_tab == "Hoàn tất lấy máu" and selected_table != "6":  # Only for tables 1–5
        display_blood_draw_completion_tab()

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

