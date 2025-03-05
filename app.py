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
    Week 1 is defined as the week containing January 1 
    (if Jan 1 isn’t Sunday, use the Sunday on or before Jan 1).
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
# Database Update & Query Functions
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
            st.error(f"Cannot code leave for {login} on week {week} {day} because status is not 'W'.")
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

def get_daywise_leaves(week, day):
    query = f"SELECT id, login, shift, {day} as Leave_Type FROM schedule WHERE week = ? AND {day} IN ('AL','SL','CL','L')"
    return pd.read_sql_query(query, conn, params=(week,))

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

def get_day_shrinkage_overview(week):
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    data = []
    for d in days:
        details = get_day_shrinkage_details(week, d)
        data.append({"Day": d, "Shrinkage (%)": details["Shrinkage (%)"], "Scheduled": details["Scheduled"], "Leaves": details["Leaves"]})
    return pd.DataFrame(data)

# ---------------------------
# Monthly Report Function
# ---------------------------
def get_monthly_report(month, year):
    df = pd.read_sql_query("SELECT * FROM schedule", conn)
    total_scheduled = 0
    total_leaves = 0
    details_list = []
    for idx, row in df.iterrows():
        week = row["week"]
        week_dates = get_week_dates_us(week, year)
        for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
            date_obj = week_dates[day]
            if date_obj.month == month:
                if row[day] != "OFF":
                    total_scheduled += 1
                    if row[day] in ("AL", "SL", "CL", "L"):
                        total_leaves += 1
                        details_list.append({
                            "Week": week,
                            "Day": day,
                            "Date": date_obj.strftime("%Y-%m-%d"),
                            "Status": row[day]
                        })
    shrinkage = (total_leaves / total_scheduled * 100) if total_scheduled > 0 else 0
    summary = {"Month": month, "Year": year, "Total Scheduled": total_scheduled, "Total Leaves": total_leaves, "Shrinkage (%)": round(shrinkage, 2)}
    details_df = pd.DataFrame(details_list)
    return summary, details_df

# ---------------------------
# Goal Analysis Function
# ---------------------------
def analyze_goal_for_week(week, goal):
    """
    For a selected week, calculates:
    - Total scheduled days and total leaves.
    - Allowed leaves to meet the goal (allowed = total_scheduled * (goal/100)).
    - Difference between current leaves and allowed leaves.
    
    Returns a dictionary with these values and a recommendation.
    """
    df_overview = get_weekly_shrinkage_overview()
    row = df_overview[df_overview["Week"] == week]
    if row.empty:
        return None
    row = row.iloc[0]
    total_scheduled = row["Total Scheduled"]
    current_leaves = row["Total Leaves"]
    allowed_leaves = (goal / 100) * total_scheduled
    result = {
        "Total Scheduled": total_scheduled,
        "Current Leaves": current_leaves,
        "Allowed Leaves": allowed_leaves,
    }
    if current_leaves > allowed_leaves:
        result["Action"] = f"Cancel approximately {current_leaves - allowed_leaves:.0f} leave(s) to meet your goal."
    elif current_leaves < allowed_leaves:
        result["Action"] = f"You can approve up to {allowed_leaves - current_leaves:.0f} additional leave(s) and still meet your goal."
    else:
        result["Action"] = "Your current shrinkage meets the goal exactly."
    return result

# ---------------------------
# Main Navigation: Dashboard, Schedule Management, Reports
# ---------------------------
main_menu = st.sidebar.radio("Navigation", ["Dashboard", "Schedule Management", "Reports"])

# ---------- Dashboard ----------
if main_menu == "Dashboard":
    st.title("Dashboard")
    st.markdown("### Overview and Interactive Analytics")
    
    # Overall Weekly Shrinkage Overview
    df_shrink = get_weekly_shrinkage_overview()
    if not df_shrink.empty:
        st.subheader("Weekly Shrinkage Overview")
        st.dataframe(df_shrink)
        fig = px.bar(df_shrink, x="Week", y="Shrinkage (%)", title="Weekly Shrinkage Percentage")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No schedule data available for analytics.")
    
    # Weekly Goal Analysis
    st.markdown("### Weekly Goal Analysis")
    goal_value = st.number_input("Enter your weekly shrinkage goal (%)", value=5.0, step=0.1, key="weekly_goal")
    selected_week_goal = st.number_input("Enter Week Number for Goal Analysis", min_value=1, step=1, value=1, key="goal_week")
    analysis = analyze_goal_for_week(selected_week_goal, goal_value)
    if analysis:
        st.write(f"Total Scheduled Days: {analysis['Total Scheduled']}")
        st.write(f"Current Leaves: {analysis['Current Leaves']}")
        st.write(f"Allowed Leaves (to meet goal of {goal_value}%): {analysis['Allowed Leaves']:.2f}")
        st.markdown(f"**Recommendation:** {analysis['Action']}")
    else:
        st.info("No data available for the selected week for goal analysis.")
    
    # Day-wise Shrinkage Analysis for a selected week
    st.markdown("### Day-wise Shrinkage Analysis")
    selected_week_for_day = st.number_input("Enter Week Number for Day-wise Analysis", min_value=1, step=1, value=1, key="day_shrink_week")
    df_day_shrink = get_day_shrinkage_overview(selected_week_for_day)
    st.dataframe(df_day_shrink)
    fig_day = px.bar(df_day_shrink, x="Day", y="Shrinkage (%)",
                     title=f"Day-wise Shrinkage for Week {selected_week_for_day}",
                     labels={"Shrinkage (%)": "Shrinkage (%)", "Day": "Day"})
    st.plotly_chart(fig_day, use_container_width=True)

# ---------- Schedule Management ----------
elif main_menu == "Schedule Management":
    st.title("Schedule Management")
    sub_menu = st.sidebar.radio("Options", ["Schedule Setup", "Leaves & Shrinkage"])
    
    # --- Schedule Setup ---
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
                        st.error(f"Missing columns in Excel file: {', '.join(missing)}")
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
    
    # --- Leaves & Shrinkage ---
    elif sub_menu == "Leaves & Shrinkage":
        st.header("Leaves & Shrinkage")
        c = conn.cursor()
        c.execute("SELECT DISTINCT login FROM schedule")
        all_logins = [row[0] for row in c.fetchall()]
        if all_logins:
            selected_login = st.selectbox("Select CSA Login", all_logins)
            c.execute("SELECT DISTINCT week FROM schedule WHERE login = ?", (selected_login,))
            available_weeks = [row[0] for row in c.fetchall()]
            if not available_weeks:
                st.info("No schedule data found for the selected login.")
            else:
                selected_week = st.selectbox("Select Week", available_weeks)
                selected_year = st.number_input("Enter Year", value=datetime.date.today().year, step=1)
                df_schedule = pd.read_sql_query("SELECT * FROM schedule WHERE login = ? AND week = ?", conn, params=(selected_login, selected_week))
                if not df_schedule.empty:
                    schedule_record = df_schedule.iloc[0]
                    computed_dates = get_week_dates_us(selected_week, selected_year)
                    display_schedule = {}
                    available_leave_options = []
                    for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        header = f"{day} ({computed_dates[day].strftime('%Y-%m-%d')})"
                        value = schedule_record[day]
                        display_schedule[header] = value
                        if value == "W":
                            available_leave_options.append(header)
                    st.write(f"Schedule for **{selected_login}** (Week {selected_week}, Year {selected_year}):")
                    st.table(pd.DataFrame([display_schedule]))
                    selected_leave_headers = st.multiselect("Select Date(s) for Leave", available_leave_options)
                    if selected_leave_headers:
                        leave_type = st.radio("Select Leave Type", ["AL", "SL", "CL", "L"])
                        annotation = st.text_area("Annotation (Optional)")
                        if st.button("Submit Leave"):
                            for header in selected_leave_headers:
                                day_abbr = header.split()[0]
                                update_leave(selected_login, selected_week, day_abbr, leave_type, annotation)
                    else:
                        st.info("No available work days selected for leave coding.")
                else:
                    st.info("No schedule record found for the selected login and week.")
        else:
            st.info("No CSA schedule data available. Please add schedule first.")
        
        st.subheader("Shrinkage Calculation for a Week")
        calc_week = st.number_input("Enter Week Number to calculate shrinkage", min_value=1, step=1, key="calc_week")
        year_calc = st.number_input("Enter Year for Calculation", value=datetime.date.today().year, step=1, key="calc_year")
        if st.button("Calculate Shrinkage"):
            df_overview = get_weekly_shrinkage_overview()
            st.write("### Overall Weekly Shrinkage Overview")
            st.dataframe(df_overview[df_overview['Week'] == calc_week])
            st.markdown("#### Day-wise Shrinkage Details")
            for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                details = get_day_shrinkage_details(calc_week, d)
                with st.expander(f"{d} Details"):
                    st.write(f"Scheduled: {details['Scheduled']}, Leaves: {details['Leaves']}, Shrinkage: {details['Shrinkage (%)']}%")
                    if details["Details"]:
                        st.table(pd.DataFrame(details["Details"]))
                    else:
                        st.write("No leave records for this day.")

# ---------- Reports ----------
elif main_menu == "Reports":
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
        selected_month = st.selectbox("Select Month", list(range(1,13)), format_func=lambda x: datetime.date(1900, x, 1).strftime('%B'))
        report_year = st.number_input("Enter Year", value=datetime.date.today().year, step=1, key="report_year")
        goal_monthly = st.number_input("Enter your monthly shrinkage goal (%)", value=5.0, step=0.1, key="monthly_goal")
        if st.button("Generate Monthly Report"):
            def get_monthly_report(month, year):
                df = pd.read_sql_query("SELECT * FROM schedule", conn)
                total_scheduled = 0
                total_leaves = 0
                details_list = []
                for idx, row in df.iterrows():
                    week = row["week"]
                    week_dates = get_week_dates_us(week, year)
                    for day in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                        date_obj = week_dates[day]
                        if date_obj.month == month:
                            if row[day] != "OFF":
                                total_scheduled += 1
                                if row[day] in ("AL", "SL", "CL", "L"):
                                    total_leaves += 1
                                    details_list.append({
                                        "Week": week,
                                        "Day": day,
                                        "Date": date_obj.strftime("%Y-%m-%d"),
                                        "Status": row[day]
                                    })
                shrinkage = (total_leaves / total_scheduled * 100) if total_scheduled > 0 else 0
                summary = {"Month": month, "Year": year, "Total Scheduled": total_scheduled, "Total Leaves": total_leaves, "Shrinkage (%)": round(shrinkage, 2)}
                details_df = pd.DataFrame(details_list)
                return summary, details_df
            summary, details_df = get_monthly_report(selected_month, report_year)
            st.markdown("### Monthly Summary")
            st.write(summary)
            if summary["Shrinkage (%)"] <= goal_monthly:
                st.success("Monthly goal met! Shrinkage is within target.")
            else:
                st.error("Monthly goal not met! Shrinkage exceeds target.")
            st.markdown("### Detailed Report")
            st.dataframe(details_df)

