import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import io

# ---------------------
# DATABASE SETUP
# ---------------------
conn = sqlite3.connect('csa_data.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        week INTEGER,
        metric1 REAL,
        metric2 REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# ---------------------
# STREAMLIT APP SETUP
# ---------------------
st.title("CSA Performance Dashboard")
st.write("This dashboard displays performance data, allows filtering by login and week number, compares weekly improvements, and lets you send your data via email.")

# ---------------------
# SESSION STATE INITIALIZATION
# ---------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# ---------------------
# USER LOGIN SECTION
# ---------------------
if not st.session_state.logged_in:
    st.subheader("Login")
    username_input = st.text_input("Enter your CSA login")
    password_input = st.text_input("Enter your password", type="password")
    
    if st.button("Login"):
        if username_input and password_input:  # For demo purposes; implement secure auth in production
            st.session_state.logged_in = True
            st.session_state.username = username_input
            st.success(f"Welcome, {username_input}!")
        else:
            st.error("Please enter both your login and password.")
    st.stop()  # Stop execution until login is successful

# ---------------------
# LOAD DATA FROM EXCEL
# ---------------------
st.subheader("Load Performance Data")
try:
    df = pd.read_excel("csa_performance.xlsx")
    st.success("Excel data loaded successfully!")
    st.write("Data loaded from Excel:", df.head())
except Exception as e:
    st.error(f"Error loading Excel file: {e}")
    st.stop()

# ---------------------
# OPTIONAL: SAVE EXCEL DATA TO DATABASE
# ---------------------
st.write("Saving Excel data to database (if needed)...")
for _, row in df.iterrows():
    cursor.execute('''
        INSERT INTO performance (username, week, metric1, metric2)
        VALUES (?, ?, ?, ?)
    ''', (row["Username"], row["Week"], row["Metric1"], row["Metric2"]))
conn.commit()
st.success("Data saved to the database.")

# ---------------------
# FILTER DATA
# ---------------------
st.subheader("Filter Performance Data")
st.write("Available Usernames:", df["Username"].unique())
st.write("Available Weeks:", df["Week"].unique())

filter_login = st.text_input("Filter by CSA Login", value=st.session_state.username)
week_list = sorted(df["Week"].unique())
filter_week = st.selectbox("Select Week", week_list)

filtered_df = df[(df["Username"] == filter_login) & (df["Week"] == filter_week)]
st.write("Filtered Performance Data:")
st.dataframe(filtered_df)

# ---------------------
# DATA VISUALIZATION WITH SELECTABLE METRIC
# ---------------------
st.subheader("Weekly Performance Comparison")
selected_metric = st.selectbox("Select Metric", ["Metric1", "Metric2"])

csa_data = df[df["Username"] == filter_login].sort_values("Week")
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(csa_data["Week"], csa_data[selected_metric], marker="o", label=selected_metric)
ax.set_xlabel("Week")
ax.set_ylabel(selected_metric)
ax.set_title(f"Week-on-Week {selected_metric} Comparison")
ax.legend()
st.pyplot(fig)

st.subheader("Detailed Summary")
summary = csa_data.groupby("Week")[selected_metric].mean().reset_index()
st.dataframe(summary)

# ---------------------
# RETRIEVE UNIQUE SAVED DATA (For Email Attachment)
# ---------------------
saved_df = pd.read_sql_query("SELECT * FROM performance ORDER BY timestamp DESC", conn)
saved_df_unique = saved_df.drop_duplicates(subset=["username", "week", "metric1", "metric2"], keep="last")

def send_email(sender_email, sender_password, recipient_email, subject, body, attachment_df=None, attachment_filename="data.csv"):
    # Create a multipart message (allows both text and attachments)
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject

    # Attach the email body (plain text)
    msg.attach(MIMEText(body, "plain"))

    # If an attachment (e.g., a DataFrame) is provided, convert it to CSV and attach it
    if attachment_df is not None:
        # Create an in-memory text buffer
        csv_buffer = io.StringIO()
        # Convert the DataFrame to CSV format and write it to the buffer
        attachment_df.to_csv(csv_buffer, index=False)
        csv_string = csv_buffer.getvalue()

        # Create a MIMEText part for the CSV attachment
        attachment_part = MIMEText(csv_string, "plain")
        attachment_part.add_header("Content-Disposition", f"attachment; filename={attachment_filename}")
        msg.attach(attachment_part)

    # Connect to the SMTP server and send the email
    try:
        # For Gmail, use smtp.gmail.com and port 587
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()  # Upgrade the connection to a secure TLS/SSL connection
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# ---------------------
# SEND EMAIL SECTION
# ---------------------
st.subheader("Send Email with Your Data")

with st.form("send_email_form"):
    sender_email = st.text_input("shaikhsufiyan22@gmail.com")
    sender_password = st.text_input("Sender Password", type="galaxycom")
    recipient_email = st.text_input("Recipient Email")
    email_subject = st.text_input("Email Subject", value="Your CSA Performance Data")
    email_body = st.text_area("Email Body", value="Please find attached your CSA performance data.")
    submitted = st.form_submit_button("Send Email")
    
    if submitted:
        # Call the send_email function defined earlier
        def send_email(sender_email, sender_password, recipient_email, subject, body, attachment_df=None, attachment_filename="data.csv"):
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = recipient_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            if attachment_df is not None:
                csv_buffer = io.StringIO()
                attachment_df.to_csv(csv_buffer, index=False)
                csv_string = csv_buffer.getvalue()
                attachment_part = MIMEText(csv_string, "plain")
                attachment_part.add_header("Content-Disposition", f"attachment; filename={attachment_filename}")
                msg.attach(attachment_part)
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
                server.quit()
                return True
            except Exception as e:
                st.error(f"Error sending email: {e}")
                return False
        
        if send_email(sender_email, sender_password, recipient_email, email_subject, email_body, attachment_df=saved_df_unique):
            st.success("Email sent successfully!")
        else:
            st.error("Failed to send email.")
