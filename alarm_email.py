import pandas as pd
import smtplib
import pandas as pd
import os
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === Config ===
CSV_DIR = 'data_folder'

# Map each file prefix to a label (friendly name for output)
PREFIX_LABELS = {
    "p129.118.107.232_output": "Lobby",
    "p129.118.107.233_output": "Room A",
    "p129.118.107.234_output": "Room B",
    "p129.118.107.235_output": "Chase Area",
    "p129.118.107.204_output": "Room C",
    "p129.118.107.205_output": "Room D"
}

# Per-column thresholds
LIMITS = {
    'Temperature': 26,
    'Pressure': 905,
    'Humidity': 50
}

# Email configuration
EMAIL_FROM = 'apd.weatherstation.alarm@gmail.com'
# === Load recipient emails from a text file ===
with open("recipients.txt", "r") as f:
    recipient_emails = [line.strip() for line in f if line.strip()]

EMAIL_SUBJECT = '⚠️ APD Lab Weather Threshold Violations Detected'

# === Collect all violations across all groups ===
all_violations = []

for prefix, label in PREFIX_LABELS.items():
    # Find newest file for the prefix
    pattern = os.path.join(CSV_DIR, f"{prefix}*.csv")
    matching_files = glob.glob(pattern)
    if not matching_files:
        continue

    latest_file = max(matching_files, key=os.path.getmtime)
    try:
        df = pd.read_csv(latest_file)
    except Exception as e:
        all_violations.append(f"❌ Failed to read {latest_file} ({label}): {e}")
        continue

    if 'Time' not in df.columns:
        all_violations.append(f"⚠️ File '{latest_file}' ({label}) is missing a 'Time' column.")
        continue

    # Check thresholds
    for col, limit in LIMITS.items():
        if col in df.columns:
            exceeded = df[df[col] > limit]
            for _, row in exceeded.iterrows():
                time = row['Time']
                value = row[col]
                all_violations.append(
                    f"[{label}] At {time}: {col} = {value} exceeded threshold of {limit}"
                )

# === If there are violations, send a summary email ===
if all_violations:
    message = MIMEMultipart()
    message['From'] = EMAIL_FROM
    message['To'] = ", ".join(recipient_emails)
    message['Subject'] = EMAIL_SUBJECT

    body = "⚠️ Threshold violations detected across monitored locations:\n\n"
    body += "\n".join(all_violations)

    message.attach(MIMEText(body, 'plain'))

    # === Send email (SMTP setup assumed) ===
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_FROM, "XXXXXXX")
            server.sendmail(EMAIL_FROM, recipient_emails, message.as_string())
        print("✅ Alert email sent.")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
else:
    print("yep working.")
