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
    restricted_tables = [str(i) for i in range(1, 6)]  # Tables 1–5 are restricted
    available_tables = []  # List to collect available table options

    # Determine availability for tables 1–5 based on active logins
    if not login_log_df.empty:
        active_tables = login_log_df[login_log_df['thoiGianLogout'] == ""]["table"].tolist()
        for table in restricted_tables:
            if table not in active_tables:
                available_tables.append(table)
    else:
        available_tables.extend(restricted_tables)  # If no log exists, all tables 1–5 are available

    # Add "Nhận mẫu" (table 6), which is always available
    available_tables.append("6")

    # Create display mapping for the dropdown
    table_display_mapping = {table: table for table in restricted_tables}
    table_display_mapping["6"] = "Nhận mẫu"

    # Reverse mapping for internal use
    display_to_internal_mapping = {v: k for k, v in table_display_mapping.items()}

    # Generate dropdown options using the display mapping
    dropdown_options = [table_display_mapping[table] for table in available_tables]

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
                st.success(f"Xin chào, {user_info['tenNhanVien']}! Đã đăng nhập vào'Nhận mẫu'.")
            else:
                st.success(f"Xin chào, {user_info['tenNhanVien']}! Đã đăng nhập vào bàn lấy máu số {selected_table}.")
        else:
            st.error("Sai thông tin User hoặc Password.")





def display_registration_tab():
    """Displays the Registration tab."""
    st.title("Đăng ký PID mới")
    pid = st.text_input("Nhập PID:")

    if st.button("Đăng ký"):
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
        else:
            st.error("Không thể lấy thông tin bệnh nhân.")


def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.title("Lấy máu")

    # Create a placeholder for content to refresh dynamically
    placeholder = st.empty()

    def refresh_content():
        # Fetch the Reception sheet data
        reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
        if reception_df.empty:
            placeholder.write("No PIDs registered yet.")
            return

        # Ensure required columns exist
        required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau", "table", "ketThucLayMau"}
        if not required_columns.issubset(reception_df.columns):
            placeholder.error(f"The sheet must contain these columns: {required_columns}")
            return

        user_name = st.session_state["user_info"]["tenNhanVien"]
        selected_table = st.session_state.get("selected_table", None)
        reception_df = reception_df.replace("", None)

        # Convert `thoiGianNhanMau` to datetime for filtering by the same day
        reception_df["thoiGianNhanMau"] = pd.to_datetime(reception_df["thoiGianNhanMau"], errors="coerce")

        # Check for duplicates within the same day
        reception_df["duplication_count"] = reception_df.groupby("PID")["thoiGianNhanMau"].rank(method="first")

        # Filter rows where the current user or unprocessed rows are shown
        filtered_df = reception_df[
            (((reception_df["thoiGianLayMau"].isna()) | (reception_df["nguoiLayMau"] == user_name)) &
            (reception_df["ketThucLayMau"] != "1")) &
            (
                # Table 4 and 5 can see all rows
                ((selected_table in ["4", "5"]) | 
                 # Other tables can only see non-duplicates or the first occurrence of a duplicate
                 (reception_df["duplication_count"] == 1))
            )
        ]
        filtered_df = filtered_df.sort_values(by="thoiGianNhanMau")

        # Display only relevant actions without showing the entire dataframe
        with placeholder.container():
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

                        # Prepare the updated values
                        updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
                        sheets_service.spreadsheets().values().update(
                            spreadsheetId=RECEPTION_SHEET_ID,
                            range=RECEPTION_SHEET_RANGE,
                            valueInputOption="USER_ENTERED",
                            body={"values": updated_values}
                        ).execute()

                        # Set session variables for Blood Draw Completion
                        st.session_state["current_pid"] = pid
                        st.session_state["current_ten_benh_nhan"] = ten_benh_nhan

                        st.success(f"Bắt đầu lấy máu cho PID {pid}. Bấm vào thẻ 'Hoàn tất lấy máu' để tiếp tục.")
            else:
                placeholder.write("Chưa có bệnh nhân.")

    # Display refresh button to reload the content
    if st.button("Refresh"):
        refresh_content()

    # Call refresh_content initially to load data
    refresh_content()




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



import time

def display_table_tab():
    """Displays the Table tab for managing PIDs without thoiGianLayMau."""
    st.title("DANH SÁCH CHỜ GỌI SỐ")
    
    # Create a placeholder for the table content
    placeholder = st.empty()
    refresh_interval = 15  # seconds

    while True:
        with placeholder.container():
            # Fetch data from the NhanMau sheet
            nhanmau_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
            if nhanmau_df.empty:
                st.write("No pending PIDs.")
            else:
                # Ensure required columns exist
                required_columns = {"PID", "tenBenhNhan", "thoiGianLayMau", "table", "ketThucLayMau"}
                if not required_columns.issubset(nhanmau_df.columns):
                    st.error(f"The sheet must contain these columns: {required_columns}")
                else:
                    # Normalize null values
                    nhanmau_df = nhanmau_df.replace("", None)  # Convert blank strings to None

                    # Filter rows where 'table' is not null and 'ketThucLayMau' is not "1"
                    filtered_df = nhanmau_df[
                        nhanmau_df["table"].notna() & (nhanmau_df["ketThucLayMau"] != "1")
                    ]

                    # Rename columns for display
                    filtered_df = filtered_df.rename(columns={
                        "PID": "Mã",
                        "tenBenhNhan": "Họ tên",
                        "table": "Bàn"
                    })

                    # Select only relevant columns for display
                    filtered_df = filtered_df[["Mã", "Họ tên", "Bàn"]]

                    # Display the table
                    if not filtered_df.empty:
                        st.write("### Thứ tự")
                        st.dataframe(filtered_df, use_container_width=True)
                    else:
                        st.write("Chưa có số thứ tự tiếp theo.")

            # Masked sleep logic (users will not see countdown)
            time.sleep(refresh_interval)

        # Clear all output within the placeholder before the next refresh
        placeholder.empty()


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

