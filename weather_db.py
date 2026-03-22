import pandas as pd
import psycopg2
import os
import re

# =========================
# CONFIG
# =========================
DATA_DIR = "/home/pi"
FILE_PREFIX = "p129.118.107.234_output_"
LAST_SENT_FILE = "last_sent_timestamp.txt"

# --- DATABASE CONFIG ---
db_host = "129.118.107.198"
db_user = "weatherman"
db_password = "raspberrypi"
db_database = "ttu_mac_local"
db_port: "5432"
db_table = "temp_humidity"

LOCATION = "Gantry room"


# =========================
# FILE HANDLING
# =========================

def get_latest_csv():

    files = [f for f in os.listdir(DATA_DIR) if f.startswith(FILE_PREFIX) and f.endswith(".csv")]

    if not files:
        return None

    # Extract timestamp from filename
    def extract_ts(filename):
        match = re.search(r'_(\d{10})\.csv$', filename)
        if match:
            return match.group(1)
        return "0"

    # Sort by timestamp
    files.sort(key=lambda f: extract_ts(f))

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
# CSV HANDLING
# =========================

def get_latest_row(csv_file):

    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    if df.empty:
        return None

    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])

    if df.empty:
        return None

    return df.iloc[-1]


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

        timestamp = pd.to_datetime(row["Time"])
        location = "Gantry Room"
        device_name = "pi_B"
        temp_c = float(row["Temperature"])
        rel_hum = float(row["Humidity"])

        cur.execute(
            """
            INSERT INTO temp_humidity (log_timestamp, log_location, device_name, temp_c, rel_hum)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (timestamp, location, device_name, temp_c, rel_hum)
        )

        conn.commit()
        conn.close()

        print(f"Inserted: {row['Time']}")

    except Exception as e:
        print(f"Database error: {e}")


# =========================
# MAIN
# =========================

def main():

    csv_file = get_latest_csv()

    if csv_file is None:
        print("No CSV files found")
        return

    print(f"Using file: {csv_file}")

    row = get_latest_row(csv_file)

    if row is None:
        print("No valid data")
        return

    last_sent = get_last_sent_timestamp()
    current_ts = str(row["Time"])

    if last_sent == current_ts:
        print("No new data (already sent)")
        return

    push_to_db(row)
    save_last_sent_timestamp(current_ts)


if __name__ == "__main__":
    main()