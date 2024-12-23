def log_user_activity(ten_nhan_vien, table, login_time=None, logout_time=None):
    """Logs user activity (login or logout) in a Google Sheet."""
    data = [[ten_nhan_vien, table, login_time, logout_time]]
    append_to_sheet(
        '1u6M5pQyeDg44QXynb79YP9Mf1V6JlIqqthKrVx-DAfA',  # Login log sheet ID
        'Sheet1',
        data
    )

def display_login_page():
    """Displays the login page."""
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Dropdown for table selection (1 to 5)
    table = st.selectbox("Select Table", options=[1, 2, 3, 4, 5])

    if st.button("Login"):
        nhanvien_df = fetch_sheet_data(NHANVIEN_SHEET_ID, NHANVIEN_SHEET_RANGE)
        user = nhanvien_df[(nhanvien_df['taiKhoan'] == username) & (nhanvien_df['matKhau'] == password)]
        if not user.empty:
            user_info = user.iloc[0].to_dict()
            st.session_state['is_logged_in'] = True
            st.session_state['user_info'] = user_info
            st.session_state['table'] = table  # Store selected table
            st.success(f"Welcome, {user_info['tenNhanVien']}!")

            # Log login activity
            vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            login_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")
            log_user_activity(user_info['tenNhanVien'], table, login_time=login_time)

        else:
            st.error("Invalid username or password.")

def display_logout():
    """Logs out the user and records the logout time."""
    user_info = st.session_state['user_info']
    vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    logout_time = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M:%S")

    # Log logout activity
    log_user_activity(user_info['tenNhanVien'], st.session_state['table'], logout_time=logout_time)

    # Clear session state
    st.session_state.clear()
    st.success("You have been logged out.")

def display_reception_tab():
    """Displays the Reception tab for managing PIDs."""
    st.write("### Reception Management")

    # Fetch data from the sheet
    reception_df = fetch_sheet_data(RECEPTION_SHEET_ID, RECEPTION_SHEET_RANGE)
    if reception_df.empty:
        st.write("No PIDs registered yet.")
        return

    # Ensure required columns exist
    required_columns = {"PID", "tenBenhNhan", "thoiGianNhanMau", "thoiGianLayMau", "nguoiLayMau", "table"}
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
        "table": "Table",
    })

    # Select only relevant columns for display
    display_df = filtered_df[["PID", "Họ tên", "Thời gian nhận mẫu", "Thời gian lấy máu", "Người lấy máu", "Table"]]

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
            table = st.session_state['table']
            reception_df.loc[reception_df["PID"] == selected_pid, "thoiGianLayMau"] = now
            reception_df.loc[reception_df["PID"] == selected_pid, "nguoiLayMau"] = user_name
            reception_df.loc[reception_df["PID"] == selected_pid, "table"] = table

            # Push updated data back to Google Sheets
            updated_values = [reception_df.columns.tolist()] + reception_df.fillna("").values.tolist()
            body = {"values": updated_values}
            sheets_service.spreadsheets().values().update(
                spreadsheetId=RECEPTION_SHEET_ID,
                range=RECEPTION_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()

            st.success(f"PID {selected_pid} marked as received with Table {table}.")

def main():
    if not st.session_state.get('is_logged_in', False):
        display_login_page()
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
            display_logout()

main()
