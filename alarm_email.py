import pandas as pd
import smtplib
import pandas as pd
import os
import json
import glob
import csv
from collections import defaultdict
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import re
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
    'Temperature': 26.5,
    #'Pressure': 905,
    #'Humidity': 60,
    'dew_point': 18
}

LIMITS_JSON = {
    "temp": 26.5,
    "RH": 50,
    "BP": 90.5,
    "diff_counts_m3": {
        "0.30 um": 1020000,
        "0.50 um": 352000,
        "1.00 um": 83200,
        "2.50 um": 83200,
        "5.00 um": 2930,
        "10.00 um": 2930
        "0.30 um": 1020000,
        "0.50 um": 352000,
        "1.00 um": 83200,
        "2.50 um": 83200,
        "5.00 um": 2930,
        "10.00 um": 2930
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

# Find the lobby and chase area prefixes from the labels dictionary
lobby_prefix = next((k for k, v in PREFIX_LABELS_CSV.items() if v.lower() == "lobby"), None)
chase_prefix = next((k for k, v in PREFIX_LABELS_CSV.items() if v.lower() == "chase area"), None)

if not lobby_prefix or not chase_prefix:
    raise ValueError("Lobby or Chase prefix not found in PREFIX_LABELS_CSV")

# Load the latest lobby and chase files
lobby_files = glob.glob(os.path.join(CSV_DIR, f"{lobby_prefix}*.csv"))
chase_files = glob.glob(os.path.join(CSV_DIR, f"{chase_prefix}*.csv"))

if not lobby_files:
    raise RuntimeError("Lobby Pi data file not found!")
if not chase_files:
    raise RuntimeError("Chase Pi data file not found!")

lobby_file = max(lobby_files, key=os.path.getmtime)
chase_file = max(chase_files, key=os.path.getmtime)

lobby_df = pd.read_csv(lobby_file)
chase_df = pd.read_csv(chase_file)

# Compare cleanroom Pis to chase
for prefix, label in PREFIX_LABELS_CSV.items():

    # Load the latest file for this cleanroom Pi
    matching_files = glob.glob(os.path.join(CSV_DIR, f"{prefix}*.csv"))
    if not matching_files:
        continue

    latest_file = max(matching_files, key=os.path.getmtime)
    print(latest_file)

    try:
        df = pd.read_csv(latest_file)
    except Exception as e:
        all_violations.append(f"❌ Failed to read {latest_file} ({label}): {e}")
        continue

    if 'Pressure' not in df.columns:
        all_violations.append(f"⚠️ File '{latest_file}' ({label}) is missing a 'Pressure' column.")
        continue

    # Truncate to the shortest matching length
    min_len = min(len(df), len(chase_df))
    df = df.iloc[:min_len].reset_index(drop=True)
    chase_trunc = chase_df.iloc[:min_len].reset_index(drop=True)

    for idx, (row_room, row_chase) in enumerate(zip(df.itertuples(), chase_trunc.itertuples())):
        # Get timestamp, fallback to row index if missing
        time = getattr(row_room, 'Time', f"row {idx}")
    
    
        # General threshold checks
        for col, limit in LIMITS_CSV.items():
            if hasattr(row_room, col) and pd.notna(getattr(row_room, col)) and float(getattr(row_room, col)) > limit:
                all_violations.append(
                    f"[{label}] At {time}: {col} = {getattr(row_room, col):.2f} exceeded threshold of {limit}"
                )
    
    
        # Pressure comparison: Room vs. Chase
        if pd.notna(row_room.Pressure) and pd.notna(row_chase.Pressure):
            delta_p = float(row_room.Pressure) - float(row_chase.Pressure)
            if delta_p < 0:
                all_violations.append(
                    f"[{label}] At {time}: Negative pressure difference ΔP = {delta_p:.2f} Pa (Room < Chase)"
                )
    
    
        # Dew point check (optional — if Temperature & Humidity present)
        if hasattr(row_room, 'Temperature') and hasattr(row_room, 'Humidity'):
            if pd.notna(row_room.Temperature) and pd.notna(row_room.Humidity):
                t = float(row_room.Temperature)
                rh = float(row_room.Humidity)
                dew_point = t - ((100 - rh) / 5)
                if dew_point > LIMITS_CSV['dew_point']:
                    all_violations.append(
                        f"[{label}] At {time}: Dew Point = {dew_point:.2f}°C exceeded threshold of {LIMITS_CSV['dew_point']}°C"
                    )

    if prefix in (lobby_prefix, chase_prefix):
        continue  # Skip lobby and chase themselves

    if prefix in (lobby_prefix, chase_prefix):
        continue  # Skip lobby and chase themselves

# Compare Chase to Lobby
min_len_chase_lobby = min(len(chase_df), len(lobby_df))
chase_trunc = chase_df.iloc[:min_len_chase_lobby].reset_index(drop=True)
lobby_trunc = lobby_df.iloc[:min_len_chase_lobby].reset_index(drop=True)

for idx, (row_chase, row_lobby) in enumerate(zip(chase_trunc.itertuples(), lobby_trunc.itertuples())):
    time = getattr(row_chase, 'Time', f"row {idx}")
    if pd.notna(row_chase.Pressure) and pd.notna(row_lobby.Pressure):
        delta_p2 = float(row_chase.Pressure) - float(row_lobby.Pressure)
        if delta_p2 < 0:
            all_violations.append(
                f"[Chase Area] At {time}: Negative pressure difference ΔP = {delta_p2:.2f} Pa (Chase < Lobby)"
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


violation_pattern = re.compile(
    r"\[(?P<room>.+?)\].*At (?P<time>[\d\-: ]+): (?P<type>[^\s=]+) = [\d\.]+ exceeded threshold"
)

# To include Dew Point line (which is phrased differently):
# [Room A] At 2025-06-15 12:02:33: Dew Point = 27.00°C exceeded threshold of 18°C
dew_point_pattern = re.compile(
    r"\[(?P<room>.+?)\].*At (?P<time>[\d\-: ]+): Dew Point = [\d\.]+ exceeded threshold"
)

particle_count_pattern = re.compile(
    r"\[(?P<label>.+?)\]\s+At\s+(?P<timestamp_str>[\d\-: ]+):\s+Particle count (?P<size>[\d\.]+\s+um)\s+=\s+(?P<value>[\d\.]+)\s+exceeded threshold of\s+(?P<limit>[\d\.]+)"
)

pressure_pattern = re.compile(
   r"\[(?P<label>.+?)\].* At (?P<time>[\d\-: ]+): Negative pressure difference ΔP = [\d\.]+ Pa (Chase < Lobby)"
)

#most_recent_per_room_type = {}
most_recent_per_room_type = defaultdict(list)

for violation in all_violations:
    # --- Extract timestamp ---
    time_match = re.search(r"At ([\d\-: ]+):", violation)
    if not time_match:
        continue

    time_str = time_match.group(1)

    try:
        time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        continue

    # --- Extract room/label ---
    room_match = re.search(r"\[(.+?)\]", violation)
    room = room_match.group(1) if room_match else "Unknown"

    # --- Extract violation type safely ---
    if "=" in violation:
        vtype = violation.split(":")[1].split("=")[0].strip()
    else:
        # For pressure difference messages etc.
        vtype = violation.split(":")[1].strip() if ":" in violation else "General"

    key = (room, vtype)
    
    most_recent_per_room_type[key].append((time_obj, violation))
        
    # Sort the list by time, most recent first
    most_recent_per_room_type[key].sort(reverse=True, key=lambda x: x[0])
        
    # Keep only the top 5
    most_recent_per_room_type[key] = most_recent_per_room_type[key][:5]
        
        #most_recent_per_room_type[key] = (time_obj, violation)

# Build reduced list to email
#summary_for_email = [v[1] for v in most_recent_per_room_type.values()]
summary_for_email = [violation for violation_list in most_recent_per_room_type.values() for _, violation in violation_list]

# --- Send the email with filtered summary ---

print("TOTAL VIOLATIONS FOUND:", len(all_violations))
print("TOTAL VIOLATIONS EMAILED:", len(summary_for_email))
if summary_for_email:
    message = MIMEMultipart()
    message['From'] = EMAIL_FROM
    message['To'] = ", ".join(recipient_emails)
    message['Subject'] = EMAIL_SUBJECT

    body = "⚠️ Most recent threshold violations per type and location:\n\n"
    body += "\n".join(sorted(summary_for_email))

    message.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, recipient_emails, message.as_string())
        print("✅ Alert email sent.")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
else:
    print("No threshold violations detected. Have a nice day.")
