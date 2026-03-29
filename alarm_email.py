import smtplib
import pandas as pd
import os
import json
import glob
import csv
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import re
import math

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

PREFIX_LABELS_JSON = {"counter_data_file": "Room B"}

# Per-column thresholds
LIMITS_CSV = {
    'Temperature': 26.5,
    #'Pressure': 905,
    #'Humidity': 60,
    'dew_point_max': 18,
    'dew_point_min': 0
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
    }
}

PRESSURE_TOL = 0.01
CHASE_OFFSET = 2.3

def compute_weekly_sensor_offsets(variable=None, reference_label="Chase Area", window_days=1):
    """
    Compute robust rolling offsets for a given variable (Pressure, Temperature, RH)
    relative to the reference sensor (default: Chase Area) over the past `window_days`.
    Returns a dict: {room_label: median_offset}.
    """
    # Gather all CSV files
    all_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))

    # Extract timestamps from all filenames
    file_dates = []
    file_map = {}  # map datetime -> list of files
    for f in all_files:
        try:
            ts_str = os.path.basename(f).split("_")[-1].replace(".csv", "")
            ts = datetime.strptime(ts_str, "%Y%m%d%H")
            file_dates.append(ts)
            file_map.setdefault(ts, []).append(f)
        except ValueError:
            continue

    if not file_dates:
        print("No valid CSV timestamps found!")
        return {}

    end_time = max(file_dates)
    start_time = end_time - timedelta(days=window_days)

    # Storage for variable differences per room per hour
    delta_data = defaultdict(list)

    # Loop over each hour in the window
    for ts in file_dates:
        if not (start_time <= ts <= end_time):
            continue

        # Find reference (Chase) file for this hour
        ref_file = next(
            (f for f in file_map.get(ts, []) if os.path.basename(f).startswith("p129.118.107.235_output")),
            None
        )
        if not ref_file:
            continue

        try:
            df_ref = pd.read_csv(ref_file)
            df_ref["Time"] = pd.to_datetime(df_ref["Time"], errors="coerce")
            df_ref = df_ref.dropna(subset=["Time", variable])
            ref_val = df_ref[variable].median()
        except Exception:
            continue

        # Process other rooms for this hour
        for f in file_map.get(ts, []):
            room_label = None
            for prefix, label in PREFIX_LABELS_CSV.items():
                if os.path.basename(f).startswith(prefix):
                    room_label = label
                    break
            if room_label is None or room_label == reference_label:
                continue

            try:
                df_room = pd.read_csv(f)
                df_room["Time"] = pd.to_datetime(df_room["Time"], errors="coerce")
                df_room = df_room.dropna(subset=["Time", variable])
                room_val = df_room[variable].median()
            except Exception:
                continue

            delta_hour = room_val - ref_val
            delta_data[room_label].append(delta_hour)

    # Remove outliers and compute final offset
    offsets = {}
    for room, values in delta_data.items():
        if not values:
            offsets[room] = 0.0
            continue

        series = pd.Series(values)
        Q1, Q3 = series.quantile([0.25, 0.75])
        IQR = Q3 - Q1
        filtered = series[(series >= Q1 - 1.5 * IQR) & (series <= Q3 + 1.5 * IQR)]

        if filtered.empty:
            offsets[room] = round(series.median(), 2)
        else:
            offsets[room] = round(filtered.median(), 2)

    return offsets

#DELTA_P_OFFSETS = compute_weekly_sensor_offsets(variable="Pressure")
DELTA_P_OFFSETS_hPa = {
        'Room A': -0.35,
        'Room B': -0.29,
        'Room C': -0.18,
        'Room D': -0.47,
        'Lobby': -0.38
        }

DELTA_P_OFFSETS = {room: (val * 100) / 248.8 for room, val in DELTA_P_OFFSETS_hPa.items()}

#TEMP_OFFSETS = compute_weekly_sensor_offsets(variable="Temperature")
TEMP_OFFSETS = {
        'Room A': -0.81,
        'Room B': -0.56,
        'Room C': -1.88,
        'Room D': -1.49,
        'Lobby': -1.55
        }

#RH_OFFSETS = compute_weekly_sensor_offsets(variable="Humidity")
RH_OFFSETS = {
        'Room A': 0.0,
        'Room B': 0.16,
        'Room C': 0.05,
        'Room D': 0.31,
        'Lobby': 0.33,
        }

print("delta p offsets = ", DELTA_P_OFFSETS)
print("temperate offsets = ", TEMP_OFFSETS)
print("RH offsets = ", RH_OFFSETS)

EXPECTED_HEADER = "Time,Temperature,Humidity,Pressure\n"

def ensure_header(filepath):
    if not os.path.exists(filepath):
        return

    with open(filepath, 'r') as f:
        first_line = f.readline()

    # If file is empty
    if first_line == "":
        with open(filepath, 'w') as f:
            f.write(EXPECTED_HEADER)
        return

    # If header already correct
    if first_line.startswith("Time,"):
        return

    # Otherwise prepend header
    with open(filepath, 'r') as f:
        contents = f.read()

    with open(filepath, 'w') as f:
        f.write(EXPECTED_HEADER)
        f.write(contents)

# === Operational Safeguards ===
TIME_TOLERANCE = pd.Timedelta("2min")
STALE_LIMIT = pd.Timedelta("2hr")   # absolute staleness check
WORKDAY_START_HOUR = 9
WORKDAY_END_HOUR = 17

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

ensure_header(lobby_file)
lobby_df = pd.read_csv(lobby_file)

ensure_header(chase_file)
chase_df = pd.read_csv(chase_file)

# Ensure numeric
chase_df["Temperature"] = pd.to_numeric(chase_df["Temperature"], errors="coerce")

# Apply chase-specific correction
chase_df["Temperature"] = chase_df["Temperature"] - CHASE_OFFSET

# --- Absolute freshness check for lobby & chase ---
for name, df_check in [("Lobby", lobby_df), ("Chase Area", chase_df)]:
    if 'Time' in df_check.columns:
        df_check['Time'] = pd.to_datetime(df_check['Time'], errors='coerce')
        df_check = df_check.dropna(subset=['Time'])
        if not df_check.empty:
            latest_time = df_check['Time'].max()
            if pd.Timestamp.now() - latest_time > STALE_LIMIT:
                print(f"⚠️ {name} data is STALE. Last update: {latest_time}")
        else:
            print(f"⚠️ {name} has no valid timestamps!")

# Compare cleanroom Pis to chase
for prefix, label in PREFIX_LABELS_CSV.items():
    if prefix == lobby_prefix:
        continue

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
    
    # --- Freshness check ---
    if 'Time' in df.columns:
        try:
            latest_timestamp = datetime.strptime(df['Time'].iloc[-1], "%Y-%m-%d %H:%M:%S")
            if latest_timestamp < datetime.now() - timedelta(hours=1):
                print(f"⚠️ Skipping {label} — no data in the last hour.")
                continue
        except Exception:
            print(f"⚠️ Could not parse timestamps for {label}. Skipping freshness check.")

    if 'Pressure' not in df.columns:
        all_violations.append(f"⚠️ File '{latest_file}' ({label}) is missing a 'Pressure' column.")
        continue

    # rely on timestamps, not length for comparing info between chase and lobby
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    chase_df['Time'] = pd.to_datetime(chase_df['Time'], errors='coerce')

    df = df.dropna(subset=['Time']).sort_values('Time')
    chase_df = chase_df.dropna(subset=['Time']).sort_values('Time')

    if df.empty or chase_df.empty:
        print(f"⚠️ Skipping {label} comparison — empty dataframe after timestamp cleaning.")
        continue

    merged = pd.merge_asof(
        df,
        chase_df.rename(columns={"Time": "Time_chase"}),
        left_on='Time',
        right_on='Time_chase',
        direction='nearest',
        tolerance=TIME_TOLERANCE,
        suffixes=('_room', '_chase')
    )

    if merged['Pressure_chase'].isna().all():
        print(f"⚠️ No valid Chase data within tolerance window for {label}")

    for row in merged.itertuples():

        time_room = getattr(row, 'Time', None)
        time_chase = getattr(row, 'Time_chase', None)

        p_room1 = getattr(row, 'Pressure_room', None)
        p_chase1 = getattr(row, 'Pressure_chase', None)

        p_room = (p_room1*100)/248.8
        p_chase = (p_chase1*100)/248.8

        # ---- Timestamp mismatch warning ----
        if pd.notna(time_chase) and pd.notna(time_room):
            delta_time = abs(time_chase - time_room)
            if delta_time > TIME_TOLERANCE:
                print(f"⚠️ Chase–Lobby timestamp mismatch: {delta_time}")

        # ---- Threshold checks for temperature with offset ----
        temp_offset = TEMP_OFFSETS.get(label, 0)  # similar to DELTA_P_OFFSETS
        raw_temp = getattr(row, "Temperature_room", None)

        if raw_temp is not None and pd.notna(raw_temp):
            corrected_temp = float(raw_temp) - temp_offset  # apply offset

            if label == "Chase Area":
                corrected_temp -= CHASE_OFFSET

            if corrected_temp > LIMITS_CSV['Temperature']:
                all_violations.append(
                    f"[{label}] At {time_room}: Temperature = {corrected_temp:.2f} exceeded threshold of {LIMITS_CSV['Temperature']}"
                )

        # ---- Pressure difference ----
        if pd.notna(p_room) and pd.notna(p_chase):

            delta_p = float(p_room) - float(p_chase)

            offset = DELTA_P_OFFSETS.get(label, 0)
            delta_p_corrected = delta_p - offset

            if delta_p_corrected < -PRESSURE_TOL:
                all_violations.append(
                    f"[{label}] At {time_room}: negative pressure difference ΔP = {delta_p_corrected:.2f} inH2O (Room < Chase)"
                )
            
            elif -PRESSURE_TOL <= delta_p_corrected < 0:
                print(
                    f"[{label}] At {time_room}: ΔP = {delta_p_corrected:.2f} inH2O within tolerance (sensor noise)"
                    )
            
        # ---- Dew point ----
        temp = getattr(row, 'Temperature_room', None)
        hum = getattr(row, 'Humidity_room', None)

        temp_corrected = temp - TEMP_OFFSETS.get(label, 0)
        rh_corrected   = hum - RH_OFFSETS.get(label, 0)

        if temp is not None and pd.notna(temp) and hum is not None and pd.notna(hum):
            t = float(temp_corrected)
            rh = float(rh_corrected)
            
            a = 17.625
            b = 243.04

            gamma = math.log(rh / 100.0) + (a * t) / (b + t)
            dew_point_val = (b * gamma) / (a - gamma)

            if dew_point_val > LIMITS_CSV['dew_point_max']:
                all_violations.append(
                        f"[{label}] At {time_room}: HEIGHTEND CONDENSATION RISK --> Dew Point = {dew_point_val:.2f}°C exceeded threshold of {LIMITS_CSV['dew_point_max']}°C. Please do not leave modules out for extended periods of time."
                )
            elif dew_point_val < LIMITS_CSV['dew_point_min']:
                all_violations.append(
                        f"[{label}] At {time_room}: HEIGHTEND ESD RISK --> Dew Point = {dew_point_val:.2f}°C was below {LIMITS_CSV['dew_point_min']}°C. Please take care when handling modules."
                )

# Compare Chase to Lobby
chase_df['Time'] = pd.to_datetime(chase_df['Time'], errors='coerce')
lobby_df['Time'] = pd.to_datetime(lobby_df['Time'], errors='coerce')

chase_df = chase_df.dropna(subset=['Time']).sort_values('Time')
lobby_df = lobby_df.dropna(subset=['Time']).sort_values('Time')

merged_chase_lobby = pd.merge_asof(
    chase_df,
    lobby_df.rename(columns={"Time": "Time_lobby"}),
    left_on='Time',
    right_on='Time_lobby',
    direction='nearest',
    tolerance=TIME_TOLERANCE,
    suffixes=('_chase', '_lobby')
)

if merged_chase_lobby['Pressure_lobby'].isna().all():
    print("⚠️ No valid Lobby data within tolerance window for Chase comparison")

for row in merged_chase_lobby.itertuples():

    time_chase = getattr(row, 'Time', None)
    time_lobby = getattr(row, 'Time_lobby', None)

    p_chase1 = getattr(row, 'Pressure_chase', None)
    p_lobby1 = getattr(row, 'Pressure_lobby', None)

    p_chase = (p_chase1*100)/248.8
    p_lobby = (p_lobby1*100)/248.8

    if pd.notna(time_chase) and pd.notna(time_lobby):
        delta_time = abs(time_chase - time_lobby)
        if delta_time > TIME_TOLERANCE:
            print(f"⚠️ Chase–Lobby timestamp mismatch: {delta_time}")

    if pd.notna(p_chase) and pd.notna(p_lobby):
        delta_p = float(p_chase) - float(p_lobby)
        
        offset = DELTA_P_OFFSETS.get(label, 0)
        delta_p_corrected = delta_p - offset
        if delta_p_corrected < -PRESSURE_TOL:
            all_violations.append(
                f"[Chase Area] At {time_chase}: Negative pressure difference ΔP = {delta_p_corrected:.2f} inH2O (Chase < Lobby)"
            )
        
        elif -PRESSURE_TOL <= delta_p_corrected < 0:
                print(
                    f"[{label}] At {time_room}: ΔP = {delta_p_corrected:.2f} inH2O within tolerance (sensor noise)"
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
            lines = f.readlines()

            cutoff = datetime.now() - timedelta(minutes=60)

            for line in lines:
                data = json.loads(line.strip())

                timestamp_str = data.get("timestamp")
                if not timestamp_str:
                    continue

                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                # --- Recency safeguard ---
                if timestamp < cutoff:
                    continue

                # --- Working-hours safeguard ---
                hour = timestamp.hour
                if WORKDAY_START_HOUR <= hour < WORKDAY_END_HOUR:
                    # Skip particle alarms during normal working hours
                    print(f"Particle violation during working hours ignored at {timestamp_str}")

                # --- Particle count alerts (outside working hours only) ---
                diff_counts = data.get("diff_counts_m3", {})
                for size, limit in LIMITS_JSON["diff_counts_m3"].items():
                    measured = diff_counts.get(size, 0)
                    if measured > limit:
                        all_violations.append(
                            f"[{label}] At {timestamp_str}: "
                            f"Particle count {size} = {measured:.2f} "
                            f"exceeded threshold of {limit}"
                        )

    except Exception as e:
        all_violations.append(f"❌ Failed to read {latest_file} ({label}): {e}")
        continue

# To include Dew Point line (which is phrased differently):
# [Room A] At 2025-06-15 12:02:33: Dew Point = 27.00°C exceeded threshold of 18°C

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
    if "Particle count" in violation:
        vtype = "particle_count"
    elif "Negative pressure difference" in violation:
        vtype = "pressure_difference"
    elif "Temperature" in violation:
        vtype = "temperature"
    elif "Humidity" in violation:
        vtype = "humidity"
    elif "Dew Point" in violation:
        vtype = "dew_point"
    else:
        vtype = "general"

    key = (room, vtype)
    
    most_recent_per_room_type[key].append((time_obj, violation))
        
    # Sort the list by time, most recent first
    most_recent_per_room_type[key].sort(reverse=True, key=lambda x: x[0])
        
    # Keep only the most recent violations
    most_recent_per_room_type[key] = most_recent_per_room_type[key][:1]
        
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
