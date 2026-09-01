import smtplib
import pandas as pd
import os
import json
import glob
import csv
import argparse
import yaml
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import re
import math

# =============================================================================
# === Config loading ==========================================================
# =============================================================================
# Everything specific to a given lab's setup (paths, room names, thresholds,
# calibration numbers, email settings) lives in config.yaml, not here. This
# script should not need to be edited by a new lab adopting it — only the
# config file.

parser = argparse.ArgumentParser(description="APD Weather Station threshold alarm")
parser.add_argument(
    "--config",
    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"),
    help="Path to the YAML config file (default: config.yaml next to this script)",
)
parser.add_argument(
    "--recompute-offsets",
    action="store_true",
    help=(
        "Recompute sensor calibration offsets fresh and save them to the offsets "
        "history file. Only run this when every Pi is physically co-located with "
        "the reference sensor — do NOT use this on a normal/routine run."
    ),
)
args = parser.parse_args()


def load_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found at '{path}'. This script requires a config.yaml "
            f"(see the example shipped alongside it) — pass --config /path/to/config.yaml "
            f"if it lives somewhere else."
        )
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    if not cfg:
        raise ValueError(f"Config file at '{path}' is empty or invalid YAML.")
    return cfg


def require(cfg_section, key, context):
    """Fetch a required config key, failing loudly with a clear message if missing.
    This is deliberate: a silently-defaulted missing value (e.g. an offset of 0,
    or a threshold of 0) can quietly disable a real safety check, which is worse
    than the script refusing to run until the config is fixed."""
    if key not in cfg_section or cfg_section[key] is None:
        raise KeyError(f"Missing required config key '{key}' in '{context}' — check config.yaml.")
    return cfg_section[key]


config = load_config(args.config)

# --- Paths ---
_paths = require(config, "paths", "config.yaml")
CSV_DIR = require(_paths, "csv_dir", "paths")
EMAIL_CREDENTIALS_FILE = require(_paths, "email_credentials_file", "paths")
RECIPIENTS_FILE = require(_paths, "recipients_file", "paths")
STATE_DIR = require(_paths, "state_dir", "paths")
os.makedirs(STATE_DIR, exist_ok=True)
PRESSURE_STATE_FILE = os.path.join(STATE_DIR, "pressure_violations.json")
# Reserved for the offset-history work (#3): a JSONL file of past computed
# offsets, one line per computation, so "most recent" is just "last line".
OFFSETS_HISTORY_FILE = os.path.join(STATE_DIR, "computed_offset_history.json")
# json_dir is only required if the particle counter is enabled (checked below)
JSON_DIR = _paths.get("json_dir")

# --- Rooms / sensors ---
_rooms = require(config, "rooms", "config.yaml")
REFERENCE_ROOM = require(_rooms, "reference_room", "rooms")
ENTRANCE_ROOM = _rooms.get("entrance_room")  # optional — enables the ingress-pressure check
PREFIX_LABELS_CSV = require(_rooms, "prefix_labels_csv", "rooms")

if REFERENCE_ROOM not in PREFIX_LABELS_CSV.values():
    raise ValueError(
        f"rooms.reference_room ('{REFERENCE_ROOM}') does not match any label in "
        f"rooms.prefix_labels_csv — check config.yaml."
    )
if ENTRANCE_ROOM is not None and ENTRANCE_ROOM not in PREFIX_LABELS_CSV.values():
    raise ValueError(
        f"rooms.entrance_room ('{ENTRANCE_ROOM}') does not match any label in "
        f"rooms.prefix_labels_csv — check config.yaml, or remove entrance_room to disable "
        f"the ingress-pressure check."
    )

# Derive the CSV filename prefixes for the reference and entrance rooms once,
# rather than re-deriving them by string-matching a hardcoded label everywhere.
reference_prefix = next(k for k, v in PREFIX_LABELS_CSV.items() if v == REFERENCE_ROOM)
entrance_prefix = next((k for k, v in PREFIX_LABELS_CSV.items() if v == ENTRANCE_ROOM), None) \
    if ENTRANCE_ROOM else None

# --- Particle counter ---
_particle = config.get("particle_counter", {})
PARTICLE_COUNTER_ENABLED = _particle.get("enabled", False)
PREFIX_LABELS_JSON = _particle.get("prefix_labels_json", {}) if PARTICLE_COUNTER_ENABLED else {}

if PARTICLE_COUNTER_ENABLED and not JSON_DIR:
    raise KeyError(
        "particle_counter.enabled is true in config.yaml, but paths.json_dir is not set."
    )
if PARTICLE_COUNTER_ENABLED and not PREFIX_LABELS_JSON:
    raise KeyError(
        "particle_counter.enabled is true in config.yaml, but "
        "particle_counter.prefix_labels_json has no entries."
    )

# --- Thresholds ---
_thresholds = require(config, "thresholds", "config.yaml")
_thresholds_csv = require(_thresholds, "csv", "thresholds")
LIMITS_CSV = {
    "Temperature": require(_thresholds_csv, "temperature", "thresholds.csv"),
    "dew_point_max": require(_thresholds_csv, "dew_point_max", "thresholds.csv"),
    "dew_point_min": require(_thresholds_csv, "dew_point_min", "thresholds.csv"),
}
LIMITS_JSON = _thresholds.get("json", {}) if PARTICLE_COUNTER_ENABLED else {}
if PARTICLE_COUNTER_ENABLED and "diff_counts_m3" not in LIMITS_JSON:
    raise KeyError(
        "particle_counter.enabled is true, but thresholds.json.diff_counts_m3 is missing "
        "from config.yaml."
    )

# --- Calibration ---
_calibration = require(config, "calibration", "config.yaml")
CHASE_OFFSET = require(_calibration, "chase_offset", "calibration")  # applied to REFERENCE_ROOM's own reading
PRESSURE_TOL = require(_calibration, "pressure_tolerance", "calibration")

# --- Operational safeguards ---
_operational = require(config, "operational", "config.yaml")
TIME_TOLERANCE = pd.Timedelta(minutes=require(_operational, "time_tolerance_minutes", "operational"))
STALE_LIMIT = pd.Timedelta(hours=require(_operational, "stale_limit_hours", "operational"))
WORKDAY_START_HOUR = require(_operational, "workday_start_hour", "operational")
WORKDAY_END_HOUR = require(_operational, "workday_end_hour", "operational")
CONSECUTIVE_LIMIT = require(_operational, "consecutive_pressure_limit", "operational")

# --- Email ---
_email_cfg = require(config, "email", "config.yaml")
EMAIL_SUBJECT = require(_email_cfg, "subject", "email")
EMAIL_FROM = require(_email_cfg, "from_address", "email")
SMTP_HOST = _email_cfg.get("smtp_host", "smtp.gmail.com")
SMTP_PORT = _email_cfg.get("smtp_port", 587)


# === Consecutive pressure violation tracking ===

def load_pressure_state():
    default_state = {"consecutive_count": 0, "last_timestamp": None}
    if not os.path.exists(PRESSURE_STATE_FILE):
        return default_state
    with open(PRESSURE_STATE_FILE, "r") as f:
        content = f.read().strip()
    if not content:
        # Empty file (e.g. created with `touch`, or a previous write got cut
        # off mid-way) — treat it the same as "no state yet" rather than
        # crashing the whole run over a recoverable bookkeeping file.
        print(f"⚠️ {PRESSURE_STATE_FILE} is empty — starting fresh with a reset counter.")
        return default_state
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"⚠️ {PRESSURE_STATE_FILE} contains invalid JSON ({e}) — starting fresh with a reset counter.")
        return default_state

def save_pressure_state(state):
    with open(PRESSURE_STATE_FILE, "w") as f:
        json.dump(state, f)

def compute_weekly_sensor_offsets(variable=None, reference_label=REFERENCE_ROOM, window_days=1):
    """
    Compute robust rolling offsets for a given variable (Pressure, Temperature, RH)
    relative to the reference sensor (config: rooms.reference_room) over the past
    `window_days`. Returns a dict: {room_label: median_offset}.
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

        # Find reference file for this hour (prefix derived from config, not hardcoded)
        ref_file = next(
            (f for f in file_map.get(ts, []) if os.path.basename(f).startswith(reference_prefix)),
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

# =============================================================================
# === Offset persistence ======================================================
# =============================================================================
# Offsets are stored as one JSON object per line (JSONL) in OFFSETS_HISTORY_FILE.
# "Most recent" is simply the last line — cheap to append, cheap to read without
# parsing the whole history. Pass --recompute-offsets to run
# compute_weekly_sensor_offsets() fresh and append a new line; otherwise the
# script reads whatever the last line already says.
#
# IMPORTANT: compute_weekly_sensor_offsets() only produces a valid result when
# every Pi is physically sitting in the same room as the reference sensor
# (that's how the "true" per-sensor bias gets isolated) — it is NOT meant to be
# run during normal day-to-day operation. Recomputing is a deliberate,
# occasional calibration step, not something that happens on every run.

def load_latest_offsets(path):
    """Read the last line of the offsets JSONL file. Raises if the file is
    missing or empty — a missing offsets file should stop the script, not
    silently fall back to zero offsets (see `require()` above for why)."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No offsets history file found at '{path}'. Run this script once with "
            f"--recompute-offsets (with every Pi physically co-located with the "
            f"reference sensor) to generate an initial set of offsets."
        )
    last_line = None
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                last_line = line
    if last_line is None:
        raise ValueError(f"Offsets history file '{path}' exists but has no entries.")
    return json.loads(last_line)


def save_offsets(path, temp_offsets, rh_offsets, pressure_offsets_hpa):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "temp_offsets": temp_offsets,
        "rh_offsets": rh_offsets,
        "pressure_offsets_hpa": pressure_offsets_hpa,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


if getattr(args, "recompute_offsets", False):
    print("Recomputing sensor offsets (requires all Pis co-located with the reference sensor)...")
    fresh_temp_offsets = compute_weekly_sensor_offsets(variable="Temperature")
    fresh_rh_offsets = compute_weekly_sensor_offsets(variable="Humidity")
    fresh_pressure_offsets_hpa = compute_weekly_sensor_offsets(variable="Pressure")
    active_offsets = save_offsets(
        OFFSETS_HISTORY_FILE, fresh_temp_offsets, fresh_rh_offsets, fresh_pressure_offsets_hpa
    )
    print(f"Saved new offsets to {OFFSETS_HISTORY_FILE}")
else:
    active_offsets = load_latest_offsets(OFFSETS_HISTORY_FILE)
    print(f"Using offsets from {OFFSETS_HISTORY_FILE} (computed {active_offsets['timestamp']})")

TEMP_OFFSETS = active_offsets["temp_offsets"]
RH_OFFSETS = active_offsets["rh_offsets"]
DELTA_P_OFFSETS_hPa = active_offsets["pressure_offsets_hpa"]
DELTA_P_OFFSETS = {room: (val * 100) / 248.8 for room, val in DELTA_P_OFFSETS_hPa.items()}

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


if not os.path.exists(EMAIL_CREDENTIALS_FILE):
    raise FileNotFoundError(
        f"Email credentials file not found at '{EMAIL_CREDENTIALS_FILE}' "
        f"(paths.email_credentials_file in config.yaml)."
    )
credentials = {}
with open(EMAIL_CREDENTIALS_FILE) as f:
    for line in f:
        if '=' in line:
            key, value = line.strip().split('=', 1)
            credentials[key] = value

EMAIL_PASSWORD = credentials.get("EMAIL_PASSWORD")
if not EMAIL_PASSWORD:
    raise ValueError(f"'{EMAIL_CREDENTIALS_FILE}' did not contain an EMAIL_PASSWORD entry.")

if not os.path.exists(RECIPIENTS_FILE):
    raise FileNotFoundError(
        f"Recipients file not found at '{RECIPIENTS_FILE}' (paths.recipients_file in config.yaml)."
    )
with open(RECIPIENTS_FILE, "r") as f:
    recipient_emails = [line.strip() for line in f if line.strip()]
if not recipient_emails:
    raise ValueError(f"'{RECIPIENTS_FILE}' contains no recipient email addresses.")

# === Collect all violations across all groups ===
all_violations = []

if not entrance_prefix:
    # No entrance room configured — skip everything that depends on it below.
    # (Kept as lobby_file/lobby_df names internally for minimal diff against
    # the rest of the script; these are just "the entrance room's data", if any.)
    lobby_files = []
else:
    lobby_files = glob.glob(os.path.join(CSV_DIR, f"{entrance_prefix}*.csv"))

chase_files = glob.glob(os.path.join(CSV_DIR, f"{reference_prefix}*.csv"))

if entrance_prefix and not lobby_files:
    raise RuntimeError(f"'{ENTRANCE_ROOM}' data file not found!")
if not chase_files:
    raise RuntimeError(f"'{REFERENCE_ROOM}' (reference room) data file not found!")

chase_file = max(chase_files, key=os.path.getmtime)
ensure_header(chase_file)
chase_df = pd.read_csv(chase_file)

# Ensure numeric
chase_df["Temperature"] = pd.to_numeric(chase_df["Temperature"], errors="coerce")

# Apply reference-room-specific correction
chase_df["Temperature"] = chase_df["Temperature"] - CHASE_OFFSET

if entrance_prefix:
    lobby_file = max(lobby_files, key=os.path.getmtime)
    ensure_header(lobby_file)
    lobby_df = pd.read_csv(lobby_file)

# --- Absolute freshness check for entrance room & reference room ---
_freshness_checks = [(REFERENCE_ROOM, chase_df)]
if entrance_prefix:
    _freshness_checks.append((ENTRANCE_ROOM, lobby_df))

for name, df_check in _freshness_checks:
    if 'Time' in df_check.columns:
        df_check['Time'] = pd.to_datetime(df_check['Time'], errors='coerce')
        df_check = df_check.dropna(subset=['Time'])
        if not df_check.empty:
            latest_time = df_check['Time'].max()
            if pd.Timestamp.now() - latest_time > STALE_LIMIT:
                print(f"⚠️ {name} data is STALE. Last update: {latest_time}")
        else:
            print(f"⚠️ {name} has no valid timestamps!")

# Compare every room (including the entrance room) to the reference room
for prefix, label in PREFIX_LABELS_CSV.items():
    if entrance_prefix and prefix == entrance_prefix:
        # The entrance room is handled separately below (pressure-only,
        # ingress-risk comparison), not through this generic temp/dew-point path.
        continue

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

    # rely on timestamps, not length for comparing info between rooms
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
        print(f"⚠️ No valid {REFERENCE_ROOM} data within tolerance window for {label}")

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
                print(f"⚠️ {label}–{REFERENCE_ROOM} timestamp mismatch: {delta_time}")

        # ---- Threshold checks for temperature with offset ----
        temp_offset = TEMP_OFFSETS.get(label, 0)
        raw_temp = getattr(row, "Temperature_room", None)

        if raw_temp is not None and pd.notna(raw_temp):
            corrected_temp = float(raw_temp) + temp_offset

            if label == REFERENCE_ROOM:
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

            if -PRESSURE_TOL <= delta_p_corrected < 0:
                print(
                    f"[{label}] At {time_room}: ΔP = {delta_p_corrected:.2f} inH2O within tolerance (sensor noise)"
                    )

        # ---- Dew point ----
        temp = getattr(row, 'Temperature_room', None)
        hum = getattr(row, 'Humidity_room', None)

        temp_corrected = temp + TEMP_OFFSETS.get(label, 0)
        rh_corrected   = hum + RH_OFFSETS.get(label, 0)

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

            #elif dew_point_val < LIMITS_CSV['dew_point_min']:
            #    all_violations.append(
            #            f"[{label}] At {time_room}: HEIGHTEND ESD RISK --> Dew Point = {dew_point_val:.2f}°C was below {LIMITS_CSV['dew_point_min']}°C. Please take care when handling modules."
            #    )

# Compare reference room to entrance room (ingress-pressure risk) — only if
# an entrance room is configured.
if entrance_prefix:
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
        print(f"⚠️ No valid {ENTRANCE_ROOM} data within tolerance window for {REFERENCE_ROOM} comparison")

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
                print(f"⚠️ {REFERENCE_ROOM}–{ENTRANCE_ROOM} timestamp mismatch: {delta_time}")

        if pd.notna(p_chase) and pd.notna(p_lobby):
            delta_p = float(p_chase) - float(p_lobby)

            offset = DELTA_P_OFFSETS.get(ENTRANCE_ROOM, 0)
            delta_p_corrected = delta_p - offset

            pressure_state = load_pressure_state()

            if delta_p_corrected < -PRESSURE_TOL:
                pressure_state["consecutive_count"] += 1
                pressure_state["last_timestamp"] = str(time_chase)
                print(f"[{REFERENCE_ROOM}] Negative ΔP detected ({delta_p_corrected:.2f} inH2O). "
                      f"Consecutive count: {pressure_state['consecutive_count']}")

                if pressure_state["consecutive_count"] >= CONSECUTIVE_LIMIT:
                    all_violations.append(
                        f"[{REFERENCE_ROOM}] At {time_chase}: PROLONGED negative pressure difference — "
                        f"ΔP = {delta_p_corrected:.2f} inH2O ({REFERENCE_ROOM} < {ENTRANCE_ROOM}) for "
                        f"{pressure_state['consecutive_count']} consecutive hours"
                    )

            elif -PRESSURE_TOL <= delta_p_corrected < 0:
                print(f"[{REFERENCE_ROOM}] At {time_chase}: ΔP = {delta_p_corrected:.2f} inH2O "
                      f"within tolerance (sensor noise)")
                # Don't reset — noise readings don't clear the counter

            else:
                # Positive delta_p — pressure is fine, reset the counter
                if pressure_state["consecutive_count"] > 0:
                    print(f"[{REFERENCE_ROOM}] Pressure restored. Resetting consecutive counter.")
                pressure_state["consecutive_count"] = 0
                pressure_state["last_timestamp"] = None

            save_pressure_state(pressure_state)

# Code to handle particle counter json files (only if enabled in config.yaml)
if PARTICLE_COUNTER_ENABLED:
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
                        continue

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
else:
    print("Particle counter checks skipped (particle_counter.enabled is false in config.yaml).")

# To include Dew Point line (which is phrased differently):
# [Room A] At 2025-06-15 12:02:33: Dew Point = 27.00°C exceeded threshold of 18°C

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
    elif "PROLONGED negative pressure difference" in violation:
        vtype = "prolonged_pressure_difference"
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

# Build reduced list to email
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
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, recipient_emails, message.as_string())
        print("✅ Alert email sent.")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
else:
    print("No threshold violations detected. Have a nice day.")
