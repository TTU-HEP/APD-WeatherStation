import pandas as pd
import smtplib
import pandas as pd
import os
import json
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# === Config ===
CSV_DIR = '/home/daq2-admin/APD-WeatherStation/data_folder'
JSON_DIR = '/home/daq2-admin/APD-WeatherStation/particle_counter/data_files'

# Map each file prefix to a label (friendly name for output)
PREFIX_LABELS_CSV = {
    "p129.118.107.232_output": "Lobby",
    "p129.118.107.233_output": "Room A",
    "p129.118.107.234_output": "Room B",
    "p129.118.107.235_output": "Chase Area",
    "p129.118.107.204_output": "Room C",
    "p129.118.107.205_output": "Room D"
}

PREFIX_LABELS_JSON = {"counter_data_file": "Particle Counter (Room B)"}

# Per-column thresholds
LIMITS_CSV = {
    'Temperature': 26,
    'Pressure': 905,
    'Humidity': 60
}

LIMITS_JSON = {
    "temp": 26,
    "RH": 50,
    "BP": 90.5,
    "diff_counts_m3": {
        "0.30 um": 204000,
        "0.50 um": 70400,
        "1.00 um": 16640,
        "2.50 um": 16640,
        "5.00 um": 586,
        "10.00 um": 586
    }
}

credentials = {}
with open("/home/daq2-admin/APD-WeatherStation/email_credentials.txt") as f:
    for line in f:
        if '=' in line:
            key, value = line.strip().split('=', 1)
            credentials[key] = value

EMAIL_PASSWORD = credentials.get("EMAIL_PASSWORD")
# Email configuration
EMAIL_FROM = 'apd.weatherstation.alarm@gmail.com'
# === Load recipient emails from a text file ===
with open("/home/daq2-admin/APD-WeatherStation/recipients.txt", "r") as f:
    recipient_emails = [line.strip() for line in f if line.strip()]

EMAIL_SUBJECT = '⚠️ APD Lab Weather Threshold Violations Detected'

# === Collect all violations across all groups ===
all_violations = []

for prefix, label in PREFIX_LABELS_CSV.items():
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
    for col, limit in LIMITS_CSV.items():
        if col in df.columns:
            exceeded = df[df[col] > limit]
            for _, row in exceeded.iterrows():
                time = row['Time']
                value = row[col]
                all_violations.append(
                        f"[{label}] At {time}: {col} = {value:.2f} exceeded threshold of {limit}"
                )

# Code to handle particle counter json files
for prefix, label in PREFIX_LABELS_JSON.items():
    pattern = os.path.join(JSON_DIR, f"{prefix}*.json")
    matching_files = glob.glob(pattern)
    if not matching_files:
        continue
    latest_file = max(matching_files, key=os.path.getmtime)
    try:
        with open(latest_file, 'r') as f:
            lines=f.readlines()
            cutoff = datetime.now() - timedelta(minutes=60)
            for line in lines:
                data = json.loads(line.strip())
                timestamp_str = data.get("timestamp")
                if not timestamp_str:
                    continue
                
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")        
                if timestamp >= cutoff:
                    # Environmental alerts
                    # for key in ["temp", "RH", "BP"]:
                    #    if key in data and data[key] > LIMITS_JSON[key]:
                    #        all_violations.append(
                    #            f"[{label}] At {timestamp_str}: {key} = {data[key]:.2f} exceeded threshold of {LIMITS_JSON[key]}"
                    #        )
                    
                    # Particle count alerts
                    diff_counts = data.get("diff_counts_m3", {})
                    for size, limit in LIMITS_JSON["diff_counts_m3"].items():
                        measured = diff_counts.get(size, 0)
                        if measured > limit:
                            all_violations.append(
                                f"[{label}] At {timestamp_str}: Particle count {size} = {measured:.2f} exceeded threshold of {limit}"
                            )

    except Exception as e:
        all_violations.append(f"❌ Failed to read {latest_file} ({label}): {e}")
        continue

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
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, recipient_emails, message.as_string())
        print("✅ Alert email sent.")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
else:
    print("yep working.")
