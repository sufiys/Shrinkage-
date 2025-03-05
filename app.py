import streamlit as st
import sqlite3
import pandas as pd
import datetime
import plotly.express as px

# ---------------------------
# Initialize Session State for Bulk Upload Processing
# ---------------------------
if "bulk_processed" not in st.session_state:
    st.session_state.bulk_processed = False

# ---------------------------
# Dark/Light Mode Toggle
# ---------------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

dark_mode = st.sidebar.checkbox("Dark Mode", value=st.session_state.dark_mode)
st.session_state.dark_mode = dark_mode

if dark_mode:
    st.markdown("""
        <style>
            .main { background-color: #2f2f2f; color: #f5f5f5; }
            .stButton>button { background-color: #555; color: white; }
            h1, h2, h3, h4, h5, h6 { color: #f5f5f5; }
            .sidebar .sidebar-content { background-image: linear-gradient(#1f1f1f, #2f2f2f); color: white; }
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
            .main { background-color: #f5f5f5; color: #2f2f2f; }
            .stButton>button { background-color: #2c3e50; color: white; }
            h1, h2, h3, h4, h5, h6 { color: #2c3e50; }
            .sidebar .sidebar-content { background-image: linear-gradient(#2c3e50, #34495e); color: white; }
        </style>
    """, unsafe_allow_html=True)

# ---------------------------
# Database Initialization
# ---------------------------
def init_db():
    conn = sqlite3.connect("shrinkage.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT,
            week INTEGER,
            shift TEXT,
            Sun TEXT,
            Mon TEXT,
            Tue TEXT,
            Wed TEXT,
            Thu TEXT,
            Fri TEXT,
            Sat TEXT
        )
    """)
    conn.commit()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT,
            week INTEGER,
            day TEXT,
            leave_type TEXT,
            annotation TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# ---------------------------
# Helper Functions (Week Calculation)
# ---------------------------
def get_week_dates_us(week, year):
    """
    Compute the dates for a given week number using US-style weeks.
    Week 1 is defined as the week containing January 1 (week starts on Sunday).
    Returns a dict: {"Sun": date, "Mon": date, ..., "Sat": date}.
    """
    jan1 = datetime.date(year, 1, 1)
    offset = (jan1.weekday() + 1) % 7  
    first_sunday = jan1 - datetime.timedelta(days=offset)
    sunday = first_sunday + datetime.timedelta(days=(week - 1) * 7)
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    return {day: sunday + datetime.timedelta(days=i) for i, day in enumerate(days)}

def get_week_from_date_us(selected_date):
    year = selected_date.year
    jan1 = datetime.date(year, 1, 1)
    offset = (jan1.weekday() + 1) % 7
    first_sunday = jan1 - datetime.timedelta(days=offset)
    diff = (selected_date - first_sunday).days
    return diff // 7 + 1

# ---------------------------
# Database Update Functions
# ---------------------------
def add_schedule(login, weeks, shift, weekoffs, year):
    c = conn.cursor()
    for week in weeks:
        schedule_values = {}
        for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
            schedule_values[day] = "OFF" if day.lower() in weekoffs else "W"
        c.execute("""
            INSERT INTO schedule (login, week, shift, Sun, Mon, Tue, Wed, Thu, Fri, Sat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (login, week, shift, schedule_values["Sun"], schedule_values["Mon"],
              schedule_values["Tue"], schedule_values["Wed"], schedule_values["Thu"],
              schedule_values["Fri"], schedule_values["Sat"]))
    conn.commit()

def update_leave(login, week, day, leave_type, annotation=""):
    c = conn.cursor()
    query = f"SELECT {day} FROM schedule WHERE login = ? AND week = ?"
    c.execute(query, (login, week))
    result = c.fetchone()
    if result:
        current_val = result[0]
        if current_val == "W":
            update_query = f"UPDATE schedule SET {day} = ? WHERE login = ? AND week = ?"
            c.execute(update_query, (leave_type, login, week))
            c.execute("INSERT INTO leaves (login, week, day, leave_type, annotation) VALUES (?, ?, ?, ?, ?)",
                      (login, week, day, leave_type, annotation))
            conn.commit()
            dates = get_week_dates_us(week, year=datetime.date.today().year)
            st.success(f"Leave ({leave_type}) updated for {login} on {day} (Date: {dates[day].strftime('%Y-%m-%d')}).")
        else:
            st.error(f"Leave already coded for {login} on week {week} {day}. Please delete the existing leave to recode.")
    else:
        st.error("No schedule record found for the provided login and week.")

def delete_leave(login, week, day):
    c = conn.cursor()
    query = f"SELECT {day} FROM schedule WHERE login = ? AND week = ?"
    c.execute(query, (login, week))
    result = c.fetchone()
    if result:
        current_val = result[0]
        if current_val in ("AL", "SL", "CL", "L"):
            update_query = f"UPDATE schedule SET {day} = ? WHERE login = ? AND week = ?"
            c.execute(update_query, ("W", login, week))
            c.execute("DELETE FROM leaves WHERE login = ? AND week = ? AND day = ?", (login, week, day))
            conn.commit()
            st.success(f"Deleted leave for {login} on {day} for week {week}.")
        else:
            st.error(f"No coded leave found for {login} on {day} for week {week}.")
    else:
        st.error("No schedule record found for the provided login and week.")

def get_schedule_by_week(week):
    query = "SELECT id, login, shift, Sun, Mon, Tue, Wed, Thu, Fri, Sat FROM schedule WHERE week = ?"
    return pd.read_sql_query(query, conn, params=(week,))

def get_weekly_shrinkage_overview():
    c = conn.cursor()
    c.execute("SELECT DISTINCT week FROM schedule ORDER BY week")
    weeks = [row[0] for row in c.fetchall()]
    overview = []
    for wk in weeks:
        c.execute("SELECT Sun, Mon, Tue, Wed, Thu, Fri, Sat FROM schedule WHERE week = ?", (wk,))
        rows = c.fetchall()
        total_scheduled = sum(1 for row in rows for cell in row if cell != "OFF")
        total_leaves = sum(1 for row in rows for cell in row if cell in ("AL", "SL", "CL", "L"))
        shrinkage = (total_leaves / total_scheduled * 100) if total_scheduled > 0 else 0
        overview.append({"Week": wk, "Total Scheduled": total_scheduled, "Total Leaves": total_leaves, "Shrinkage (%)": round(shrinkage,2)})
    return pd.DataFrame(overview)

def get_day_shrinkage_details(week, day):
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM schedule WHERE week = ? AND {day} != 'OFF'", (week,))
    scheduled = c.fetchone()[0]
    c.execute(f"SELECT COUNT(*) FROM schedule WHERE week = ? AND {day} IN ('AL','SL','CL','L')", (week,))
    leaves = c.fetchone()[0]
    shrinkage = (leaves / scheduled * 100) if scheduled > 0 else 0
    c.execute("SELECT login, leave_type, annotation FROM leaves WHERE week = ? AND day = ?", (week, day))
    details = [{"login": row[0], "leave_type": row[1], "annotation": row[2]} for row in c.fetchall()]
    return {"Scheduled": scheduled, "Leaves": leaves, "Shrinkage (%)": round(shrinkage, 2), "Details": details}

def get_daywise_leaves(week, day):
    # Fetch leave details including annotations.
    query = "SELECT id, login, leave_type as Leave_Type, annotation FROM leaves WHERE week = ? AND day = ?"
    return pd.read_sql_query(query, conn, params=(week, day))

def update_schedule_day(entry_id, day, new_value):
    c = conn.cursor()
    query = f"UPDATE schedule SET {day} = ? WHERE id = ?"
    c.execute(query, (new_value, entry_id))
    c.execute("SELECT login, week FROM schedule WHERE id = ?", (entry_id,))
    row = c.fetchone()
    if row and new_value == "W":
        login, week = row
        c.execute("DELETE FROM leaves WHERE login = ? AND week = ? AND day = ?", (login, week, day))
    conn.commit()
    st.success(f"Updated schedule entry {entry_id} for {day} to {new_value}.")

def update_schedule_day_bulk(logins, weeks, days, new_value):
    c = conn.cursor()
    for login in logins:
        for week in weeks:
            for day in days:
                query = f"UPDATE schedule SET {day} = ? WHERE login = ? AND week = ?"
                c.execute(query, (new_value, login, week))
                if new_value == "W":
                    c.execute("DELETE FROM leaves WHERE login = ? AND week = ? AND day = ?", (login, week, day))
    conn.commit()
    st.success(f"Bulk updated selected entries to {new_value} on {', '.join(days)}.")

def delete_schedule_entries_bulk(logins, weeks):
    c = conn.cursor()
    for login in logins:
        for week in weeks:
            c.execute("DELETE FROM schedule WHERE login = ? AND week = ?", (login, week))
    conn.commit()
    st.success("Selected schedule entries deleted.")

def delete_entire_week_bulk(weeks):
    c = conn.cursor()
    for week in weeks:
        c.execute("DELETE FROM schedule WHERE week = ?", (week,))
    conn.commit()
    st.success("Entire week(s) deleted successfully.")

def get_leave_summary(login):
    query = "SELECT id, login, week, day, leave_type, annotation FROM leaves WHERE login = ?"
    df = pd.read_sql_query(query, conn, params=(login,))
    if not df.empty:
        df["Date"] = df.apply(lambda row: get_week_dates_us(row["week"], datetime.date.today().year)[row["day"]].strftime("%Y-%m-%d"), axis=1)
    return df

def get_day_shrinkage_overview(week):
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    data = []
    for d in days:
        details = get_day_shrinkage_details(week, d)
        data.append({"Day": d, "Shrinkage (%)": details["Shrinkage (%)"], "Scheduled": details["Scheduled"], "Leaves": details["Leaves"]})
    return pd.DataFrame(data)

# ---------------------------
# Main Navigation
# ---------------------------
menu = st.sidebar.radio("Navigation", ["Dashboard", "Schedule Management", "Reports"])

# ---------- Dashboard ----------
if menu == "Dashboard":
    st.title("Dashboard")
    st.markdown("### Overview and Interactive Analytics")
    
    # Weekly Shrinkage Overview
    df_shrink = get_weekly_shrinkage_overview()
    if not df_shrink.empty:
        st.subheader("Weekly Shrinkage Overview")
        st.dataframe(df_shrink)
        fig = px.bar(df_shrink, x="Week", y="Shrinkage (%)", title="Weekly Shrinkage Percentage")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No schedule data available for analytics.")
    
    # Day-wise Shrinkage Analysis with Absent Details
    st.markdown("### Day-wise Shrinkage Analysis")
    selected_week_for_day = st.number_input("Enter Week Number for Day-wise Analysis", min_value=1, step=1, value=1, key="day_shrink_week")
    df_day_shrink = get_day_shrinkage_overview(selected_week_for_day)
    st.dataframe(df_day_shrink)
    fig_day = px.bar(df_day_shrink, x="Day", y="Shrinkage (%)",
                     title=f"Day-wise Shrinkage for Week {selected_week_for_day}",
                     labels={"Shrinkage (%)": "Shrinkage (%)", "Day": "Day"})
    st.plotly_chart(fig_day, use_container_width=True)
    
    st.markdown("#### Absent Details by Day")
    week_dates = get_week_dates_us(selected_week_for_day, datetime.date.today().year)
    for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        details = get_day_shrinkage_details(selected_week_for_day, day)
        st.markdown(f"**{day} - {week_dates[day].strftime('%Y-%m-%d')}**")
        if details["Details"]:
            df_details = pd.DataFrame(details["Details"])
            st.table(df_details)
        else:
            st.write("No absences for this day.")

# ---------- Schedule Management ----------
elif menu == "Schedule Management":
    st.title("Schedule Management")
    sub_menu = st.sidebar.radio("Options", ["Schedule Setup", "Leaves & Shrinkage"])
    if sub_menu == "Schedule Setup":
        st.header("Schedule Setup")
        col1, col2, col3 = st.columns(3)
        with col1:
            logins_input = st.text_input("Enter CSA Logins (comma separated)")
        with col2:
            week_input = st.text_input("Enter Week Number(s) (comma separated)", "1")
        with col3:
            year_input = st.number_input("Enter Year", value=datetime.date.today().year, step=1)
        col4, col5 = st.columns(2)
        with col4:
            shift = st.text_input("Enter Shift")
        with col5:
            weekoffs = st.multiselect("Select Weekoffs (use lowercase, e.g. 'sun')", 
                                      ["sun", "mon", "tue", "wed", "thu", "fri", "sat"])
        if st.button("Submit Schedule"):
            try:
                logins = [x.strip() for x in logins_input.split(",") if x.strip()]
                weeks = [int(x.strip()) for x in week_input.split(",") if x.strip().isdigit()]
                year = int(year_input)
                if not logins:
                    st.error("Please enter at least one CSA login.")
                else:
                    for login in logins:
                        add_schedule(login, weeks, shift, weekoffs, year)
                    st.success("Schedule(s) added successfully!")
                    for wk in weeks:
                        week_dates = get_week_dates_us(wk, year)
                        st.expander(f"Week {wk} Dates").write({d: week_dates[d].strftime("%Y-%m-%d") for d in week_dates})
            except Exception as e:
                st.error(f"Error: {e}")
        if st.checkbox("Show Schedule Data"):
            c = conn.cursor()
            c.execute("SELECT DISTINCT week FROM schedule ORDER BY week")
            week_list = [row[0] for row in c.fetchall()]
            if week_list:
                selected_display_week = st.selectbox("Select Week to Display", week_list)
                df = pd.read_sql_query("SELECT * FROM schedule WHERE week = ?", conn, params=(selected_display_week,))
                if not df.empty:
                    st.dataframe(df)
                else:
                    st.info("No schedule data available for the selected week.")
            else:
                st.info("No schedule data available.")
        with st.expander("Bulk Upload Schedule via Excel"):
            st.markdown("""
            **Instructions:**  
            Upload an Excel file with the following **case‑sensitive** columns:  
            - **CSA Logins** (one or more logins separated by commas)  
            - **Week** (a single week number)  
            - **year**  
            - **shift**  
            - **Weekoff** (one or more day abbreviations separated by commas; e.g. "sun, sat")  
            **Do NOT include an 'id' column.**
            """)
            uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
            if uploaded_file is not None and not st.session_state.bulk_processed:
                try:
                    df_excel = pd.read_excel(uploaded_file)
                    required_cols = ["CSA Logins", "Week", "year", "shift", "Weekoff"]
                    missing = [col for col in required_cols if col not in df_excel.columns]
                    if missing:
                        st.error(f"Missing columns: {', '.join(missing)}")
                    else:
                        for index, row in df_excel.iterrows():
                            logins_str = row["CSA Logins"]
                            week_val = row["Week"]
                            year_val = row["year"]
                            shift_val = row["shift"]
                            weekoff_str = row["Weekoff"]
                            logins_bulk = [x.strip() for x in str(logins_str).split(",") if x.strip()]
                            weekoffs_bulk = [x.strip().lower() for x in str(weekoff_str).split(",") if x.strip()] if pd.notnull(weekoff_str) else []
                            for login in logins_bulk:
                                add_schedule(login, [int(week_val)], shift_val, weekoffs_bulk, int(year_val))
                        st.success("Bulk schedule upload processed successfully.")
                        st.session_state.bulk_processed = True
                except Exception as e:
                    st.error(f"Error processing file: {e}")
    elif sub_menu == "Leaves & Shrinkage":
        st.header("Leaves & Shrinkage")
        c = conn.cursor()
        c.execute("SELECT DISTINCT login FROM schedule")
        all_logins = [row[0] for row in c.fetchall()]
        if all_logins:
            # --- Code Leave Section with Schedule Display ---
            selected_login = st.selectbox("Select CSA Login", all_logins)
            c.execute("SELECT DISTINCT week FROM schedule WHERE login = ?", (selected_login,))
            weeks_available = sorted([row[0] for row in c.fetchall()])
            if weeks_available:
                selected_week = st.selectbox("Select Week", weeks_available)
                year_for_leave = st.number_input("Enter Year", value=datetime.date.today().year, step=1, key="year_leave")
                # Retrieve schedule for selected CSA and week
                df_schedule = pd.read_sql_query("SELECT * FROM schedule WHERE login = ? AND week = ?", conn, params=(selected_login, selected_week))
                if not df_schedule.empty:
                    dates = get_week_dates_us(selected_week, year_for_leave)
                    schedule_data = []
                    for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        schedule_data.append({
                            "Day": day,
                            "Date": dates[day].strftime('%Y-%m-%d'),
                            "Status": df_schedule.iloc[0][day]
                        })
                    df_sched_display = pd.DataFrame(schedule_data)
                    st.markdown("#### CSA Schedule")
                    st.table(df_sched_display)
                    
                    # Allow user to select dates (only from days with status "W")
                    available_options = [f"{item['Day']} ({item['Date']})" for item in schedule_data if item["Status"] == "W"]
                    if available_options:
                        selected_options = st.multiselect("Select Dates for Leaves", available_options)
                        leave_type = st.radio("Select Leave Type", ["AL", "SL", "CL", "L"])
                        annotation = st.text_area("Annotation (Optional)")
                        if st.button("Submit Leave"):
                            for option in selected_options:
                                # Extract day abbreviation from option (assumes format: "Day (YYYY-MM-DD)")
                                day_code = option.split()[0]
                                update_leave(selected_login, selected_week, day_code, leave_type, annotation)
                    else:
                        st.info("No available days for coding leave (all days already coded or off).")
                else:
                    st.error("No schedule record found for the selected CSA and week.")
            else:
                st.error("No weeks found for the selected CSA.")
            
            # --- Delete Leave Section (unchanged) ---
            st.markdown("### Delete Leave")
            selected_logins_delete = st.multiselect("Select CSA Login(s) for Leave Deletion", all_logins, key="delete_leave_logins")
            if selected_logins_delete:
                weeks_set_delete = set()
                for login in selected_logins_delete:
                    c.execute("SELECT DISTINCT week FROM schedule WHERE login = ?", (login,))
                    weeks_set_delete.update([row[0] for row in c.fetchall()])
                weeks_available_delete = sorted(list(weeks_set_delete))
                if weeks_available_delete:
                    selected_week_delete = st.selectbox("Select Week for Leave Deletion", weeks_available_delete, key="delete_leave_week")
                    selected_days_delete = st.multiselect("Select Day(s) to delete leave", ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], key="delete_leave_days")
                    if st.button("Delete Leave", key="delete_leave_button"):
                        for login in selected_logins_delete:
                            for day in selected_days_delete:
                                delete_leave(login, selected_week_delete, day)
                else:
                    st.info("No weeks available for the selected login(s).")
        else:
            st.info("No CSA schedule data available. Please add schedule first.")

# ---------- Reports ----------
elif menu == "Reports":
    st.title("Reports")
    tabs = st.tabs(["View Schedule", "Weekly Shrinkage", "Day-wise Leaves", "Delete Entry", "Update Entry", "Leave Summary", "Monthly Report"])
    with tabs[0]:
        st.subheader("View Schedule by Week")
        selected_week = st.number_input("Enter Week Number", min_value=1, step=1, key="view_week")
        year_view = st.number_input("Enter Year", value=datetime.date.today().year, step=1, key="view_year")
        df_schedule = get_schedule_by_week(selected_week)
        if not df_schedule.empty:
            week_dates = get_week_dates_us(selected_week, year_view)
            rename_dict = {d: f"{d} ({week_dates[d].strftime('%Y-%m-%d')})" for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]}
            df_schedule = df_schedule.rename(columns=rename_dict)
            df_schedule = df_schedule[["login", "shift"] + list(rename_dict.values())]
            st.dataframe(df_schedule)
        else:
            st.info("No schedule records found for the selected week.")
    with tabs[1]:
        st.subheader("Weekly Shrinkage Overview")
        df_overview = get_weekly_shrinkage_overview()
        if not df_overview.empty:
            st.dataframe(df_overview)
            st.markdown("#### Shrinkage Bar Chart")
            st.bar_chart(df_overview.set_index("Week")["Shrinkage (%)"])
        else:
            st.info("No schedule data available to calculate shrinkage.")
    with tabs[2]:
        st.subheader("Day-wise Leaves")
        leaves_week = st.number_input("Enter Week Number to view leaves", min_value=1, step=1, key="leaves_week_overview")
        day = st.selectbox("Select Day", ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], key="leaves_day_overview")
        year_leaves = st.number_input("Enter Year", value=datetime.date.today().year, step=1, key="leaves_year")
        if st.button("Show Day-wise Leaves", key="btn_leaves_overview"):
            df_day_leaves = get_daywise_leaves(leaves_week, day)
            if not df_day_leaves.empty:
                dates = get_week_dates_us(leaves_week, year_leaves)
                st.write(f"**Scheduled Date for {day}:** {dates[day].strftime('%Y-%m-%d')}")
                st.dataframe(df_day_leaves)
            else:
                st.info("No leave records found for the selected week and day.")
    with tabs[3]:
        st.subheader("Delete Entry")
        st.markdown("**Bulk Delete Options:**")
        col_del1, col_del2 = st.columns(2)
        with col_del1:
            del_logins = st.multiselect("Select CSA Login(s) to delete", 
                                        pd.read_sql_query("SELECT DISTINCT login FROM schedule", conn)["login"].tolist())
        with col_del2:
            del_weeks = st.multiselect("Select Week(s) to delete", 
                                       sorted(pd.read_sql_query("SELECT DISTINCT week FROM schedule", conn)["week"].tolist()))
        if st.button("Delete Selected Entries"):
            if del_logins and del_weeks:
                delete_schedule_entries_bulk(del_logins, del_weeks)
            else:
                st.error("Please select at least one login and one week.")
        st.markdown("---")
        st.markdown("**Bulk Delete Entire Week(s):**")
        entire_weeks = st.multiselect("Select Entire Week(s) to delete", 
                                       sorted(pd.read_sql_query("SELECT DISTINCT week FROM schedule", conn)["week"].tolist()))
        if st.button("Delete Entire Week(s)"):
            if entire_weeks:
                delete_entire_week_bulk(entire_weeks)
            else:
                st.error("Please select at least one week.")
        st.markdown("---")
        st.markdown("**Or delete individual entries:**")
        df_all = pd.read_sql_query("SELECT * FROM schedule", conn)
        st.dataframe(df_all)
        if not df_all.empty:
            ids_to_delete = st.multiselect("Select Schedule ID(s) to delete", df_all["id"].tolist())
            if st.button("Delete Selected IDs"):
                if ids_to_delete:
                    c = conn.cursor()
                    for i in ids_to_delete:
                        c.execute("DELETE FROM schedule WHERE id = ?", (i,))
                    conn.commit()
                    st.success("Selected entries deleted.")
                    df_all = pd.read_sql_query("SELECT * FROM schedule", conn)
                    st.dataframe(df_all)
                else:
                    st.error("Please select at least one Schedule ID.")
    with tabs[4]:
        st.subheader("Update Entry")
        st.markdown("**Bulk Update Options:**")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            up_logins = st.multiselect("Select CSA Login(s) to update", 
                                        pd.read_sql_query("SELECT DISTINCT login FROM schedule", conn)["login"].tolist())
        with col_up2:
            up_weeks = st.multiselect("Select Week(s) to update", 
                                       sorted(pd.read_sql_query("SELECT DISTINCT week FROM schedule", conn)["week"].tolist()))
        up_days = st.multiselect("Select Day(s) to update", ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
        new_value = st.radio("Select new value", ["W", "L"])
        if st.button("Update Selected Entries"):
            if up_logins and up_weeks and up_days:
                update_schedule_day_bulk(up_logins, up_weeks, up_days, new_value)
            else:
                st.error("Please select at least one login, one week, and one day.")
    with tabs[5]:
        st.subheader("Leave Summary")
        c = conn.cursor()
        c.execute("SELECT DISTINCT login FROM schedule")
        login_list = [row[0] for row in c.fetchall()]
        if login_list:
            summary_login = st.selectbox("Select CSA Login for Leave Summary", login_list)
            df_summary = get_leave_summary(summary_login)
            if not df_summary.empty:
                st.dataframe(df_summary)
                total_leaves = df_summary.shape[0]
                st.write(f"**Total Leaves Taken by {summary_login}:** {total_leaves}")
            else:
                st.info("No leave records found for the selected CSA.")
        else:
            st.info("No CSA logins found in schedule data.")
    with tabs[6]:
        st.subheader("Monthly Report")
        # Select multiple weeks and year for the report
        selected_weeks = st.multiselect("Select Weeks", 
                                        sorted(pd.read_sql_query("SELECT DISTINCT week FROM schedule", conn)["week"].tolist()))
        year_monthly = st.number_input("Enter Year for Report", value=datetime.date.today().year, step=1, key="monthly_year")
        if selected_weeks:
            # Query leaves for the selected weeks
            query = "SELECT * FROM leaves WHERE week IN ({seq})".format(seq=','.join(['?']*len(selected_weeks)))
            df_leaves = pd.read_sql_query(query, conn, params=selected_weeks)
            if not df_leaves.empty:
                # Compute date for each leave record
                df_leaves["Date"] = df_leaves.apply(lambda row: get_week_dates_us(row["week"], year_monthly)[row["day"]].strftime("%Y-%m-%d"), axis=1)
                st.dataframe(df_leaves[["login", "week", "day", "Date", "leave_type", "annotation"]])
            else:
                st.info("No leave records found for selected weeks.")
            
            # Weekly count of leaves
            df_group = df_leaves.groupby("week").size().reset_index(name="Leaves Count")
            st.write("### Weekly Leaves Count")
            st.dataframe(df_group)
            total_leaves = df_leaves.shape[0]
            st.write(f"**Total Leaves for selected weeks: {total_leaves}**")
            
            # Total scheduled and current shrinkage calculation for selected weeks
            df_overview = get_weekly_shrinkage_overview()
            df_selected = df_overview[df_overview["Week"].isin(selected_weeks)]
            total_scheduled = df_selected["Total Scheduled"].sum()
            current_shrinkage = (total_leaves / total_scheduled * 100) if total_scheduled > 0 else 0
            st.write(f"**Total Scheduled for selected weeks: {total_scheduled}**")
            st.write(f"**Current Shrinkage: {round(current_shrinkage,2)}%**")
            
            # Goal box to enter a target shrinkage goal
            goal = st.number_input("Enter Shrinkage Goal (%)", min_value=0.0, max_value=100.0, value=current_shrinkage, step=0.1)
            
            # Calculate maximum allowed leaves based on goal
            maximum_allowed = int(total_scheduled * (goal/100))
            required_deletion = max(0, total_leaves - maximum_allowed)
            additional_approval = max(0, maximum_allowed - total_leaves)
            st.write(f"**To achieve a shrinkage goal of {goal}%, you need to delete at least {required_deletion} leave(s).**")
            st.write(f"**Additionally, you can approve up to {additional_approval} additional leave(s) (pending) to meet that goal.**")
        else:
            st.info("Please select one or more weeks for the monthly report.")
