import pandas as pd
import psycopg2
import os
import re

# =========================
# CONFIG
# =========================
DATA_DIR = "/home/daq2-admin/APD-WeatherStation/particle_counter/data_files"
FILE_PREFIX = "counter_data_file"
LAST_SENT_FILE = "last_sent_timestamp.txt"

# --- DATABASE CONFIG ---
db_host = "129.118.107.198"
db_user = "weatherman"
db_password = "raspberrypi"
db_database = "ttu_mac_local"
db_port: "5432"
db_table = "particulate_counts"

LOCATION = "Gantry room"

# =========================
# FILE HANDLING
# =========================

def get_latest_json():
    files = [f for f in os.listdir(DATA_DIR) if f.startswith(FILE_PREFIX) and f.endswith(".json")]

    if not files:
        return None

    def extract_num(filename):
        match = re.search(r'(\d+)\.json$', filename)
        if match:
            return int(match.group(1))
        return 0

    files.sort(key=lambda f: extract_num(f))
    latest_file = files[-1]
    return os.path.join(DATA_DIR, latest_file)


# =========================
# TIMESTAMP TRACKING
# =========================

def get_last_sent_timestamp():
    if not os.path.exists(LAST_SENT_FILE):
        return None
    with open(LAST_SENT_FILE, "r") as f:
        return f.read().strip()


def save_last_sent_timestamp(ts):
    with open(LAST_SENT_FILE, "w") as f:
        f.write(str(ts))


# =========================
# JSON HANDLING
# =========================

def get_latest_row(json_file):
    try:
        with open(json_file, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            return None
        # Each line is a separate JSON object
        return json.loads(lines[-1])
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return None


# =========================
# DATABASE
# =========================

def push_to_db(row):
    try:
        conn = psycopg2.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_database
        )

        cur = conn.cursor()

        timestamp = pd.to_datetime(row["timestamp"])
        location = "Gantry Room"
        device_name = "particle counter"

        diff_counts = row["diff_counts_m3"]

        # Match channel keys to the Ch{i}_X.XXum format
        p500nm = diff_counts.get("Ch1_0.50um", 0.0)
        p1um   = diff_counts.get("Ch2_1.00um", 0.0)
        p5um   = diff_counts.get("Ch4_5.00um", 0.0)

        cur.execute(
            """
            INSERT INTO particle_counts (log_timestamp, log_location, device_name,
                prtcls_per_cubic_m_500nm, prtcls_per_cubic_m_1um, prtcls_per_cubic_m_5um)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (timestamp, location, device_name, p500nm, p1um, p5um)
        )

        conn.commit()
        conn.close()

        print(f"Inserted: {row['timestamp']}")

    except Exception as e:
        print(f"Database error: {e}")


# =========================
# MAIN
# =========================

def main():
    json_file = get_latest_json()

    if json_file is None:
        print("No JSON files found")
        return

    print(f"Using file: {json_file}")

    row = get_latest_row(json_file)

    if row is None:
        print("No valid data")
        return

    last_sent = get_last_sent_timestamp()
    current_ts = str(row["timestamp"])

    if last_sent == current_ts:
        print("No new data (already sent)")
        return

    push_to_db(row)
    save_last_sent_timestamp(current_ts)


if __name__ == "__main__":
    main()