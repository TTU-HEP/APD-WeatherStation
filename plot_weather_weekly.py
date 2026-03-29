import os
import glob
import csv
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates
from collections import defaultdict
from datetime import datetime

OUTPUT_DIR = "/home/daq2-admin/APD-WeatherStation/weekly_plots-set2/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DELTA_P_OFFSETS = {
        'Room A': -0.35,
        'Room B': -0.29,
        'Room C': -0.18,
        'Room D': -0.47,
        'Lobby': -0.38
        }

TEMP_OFFSETS = {
        'Room A': -0.81,
        'Room B': -0.56,
        'Room C': -1.88,
        'Room D': -1.49,
        'Lobby': -1.55
        }
        
RH_OFFSETS = {
        'Room A': 0.0,
        'Room B': 0.16,
        'Room C': 0.05,
        'Room D': 0.31,
        'Lobby': 0.33,
        }

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

def extract_datetime_from_filename(filename):
    """
    p129.118.107.233_output_2025121215.csv → 2025-12-12 15:00
    """
    try:
        ts = filename.split("_")[-1].replace(".csv", "")
        return datetime.strptime(ts, "%Y%m%d%H")
    except ValueError:
        return None

def make_plot_filename(label, start_date, end_date):
    start_str = start_date.strftime("%Y%m%d")
    end_str   = end_date.strftime("%Y%m%d")
    safe_label = label.replace(" ", "_")
    return f"{safe_label}_weather_{start_str}_to_{end_str}.png"

while True:
    start_str = input("Enter start datetime (YYYY-MM-DD HH): ")
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d %H')
        break
    except ValueError:
        print("Invalid start datetime.")

while True:
    end_str = input("Enter end datetime (YYYY-MM-DD HH): ")
    try:
        end_date = datetime.strptime(end_str, '%Y-%m-%d %H')
        break
    except ValueError:
        print("Invalid end datetime.")

def compute_dew_point(temp, rh):
    a = 17.625
    b = 243.04

    gamma = (a * temp / (b + temp)) + np.log(rh / 100.0)
    dew = (b * gamma) / (a - gamma)
    return dew

def pressure_diff(df1, df2):

    merged = pd.merge(
        df1[["Time","Pressure_inH2O"]],
        df2[["Time","Pressure_inH2O"]],
        on="Time",
        suffixes=("_1","_2")
    )

    merged["DeltaP"] = merged["Pressure_inH2O_1"] - merged["Pressure_inH2O_2"]

    return merged

def whats_the_weather(start_date, end_date):
    directory = "/home/daq2-admin/APD-WeatherStation/data_folder/"
    prefixes = {
        "p129.118.107.233": "Room A",
        "p129.118.107.234": "Room B",
        "p129.118.107.204": "Room C",
        "p129.118.107.205": "Room D",
        "p129.118.107.235": "Chase area",
        "p129.118.107.232": "Lobby"
    }

    grouped_files = defaultdict(list)
    output_figs = []

    all_files = glob.glob(os.path.join(directory, "*.csv"))

    # ---- Group files by PI and time window ----
    for filepath in all_files:
        filename = os.path.basename(filepath)

        file_dt = extract_datetime_from_filename(filename)
        if file_dt is None:
            continue

        if not (start_date <= file_dt <= end_date):
            continue

        for prefix in prefixes:
            if filename.startswith(prefix):
                grouped_files[prefix].append(filepath)
                break
            
    # ---- Coverage summary (move it here) ----
    print("\n--- DATA COVERAGE SUMMARY ---")
    for prefix, label in prefixes.items():
        n_files = len(grouped_files[prefix])
        if n_files == 0:
            print(f"{label}: NO FILES FOUND")
        else:
            print(f"{label}: {n_files} hourly files")

  # ---- Process each PI ----
    pi_data = {}

    for prefix, files in grouped_files.items():
        dfs = []
        for file_path in sorted(files):
            ensure_header(file_path)
            df = pd.read_csv(file_path)
            df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
            df = df.dropna(subset=["Time"])
            dfs.append(df)

        if not dfs:
            continue

        # ✅ Concatenate all files for this sensor
        df = pd.concat(dfs).sort_values("Time").reset_index(drop=True)

        label = prefixes[prefix]

        if label != "Chase area":
            p_offset  = DELTA_P_OFFSETS.get(label, 0)
            t_offset  = TEMP_OFFSETS.get(label, 0)
            rh_offset = RH_OFFSETS.get(label, 0)
        else:
            p_offset = t_offset = rh_offset = 0

        df["Temperature_corrected"] = df["Temperature"] + t_offset
        df["Humidity_corrected"]    = df["Humidity"]    + rh_offset

        # Convert first, THEN offset
        df["Pressure_inH2O"] = ((df["Pressure"] * 100) / 248.8) - p_offset

        df["DewPoint"] = compute_dew_point(df["Temperature_corrected"], df["Humidity_corrected"])

        pi_data[label] = df



    # ---- Determine overall time span for formatting ----
    all_times = pd.concat([df["Time"] for df in pi_data.values()])
    t_min = all_times.min()
    t_max = all_times.max()
    time_span = t_max - t_min


    # ---- Choose date formatter ----
    if time_span <= pd.Timedelta(days=1):
        formatter = mdates.DateFormatter("%d %H:%M")
        locator = mdates.HourLocator(interval=2)
    else:
        formatter = mdates.DateFormatter("%m-%d-%Y")
        locator = mdates.DayLocator(interval=1)


    # ---- Temperature + Dew Point plots (per room) ----
    for label, df in pi_data.items():

        fig, ax = plt.subplots(figsize=(12,6))

        ax.plot(df["Time"], df["Temperature_corrected"], 'r.', ms=3, label="Temperature")
        ax.plot(df["Time"], df["DewPoint"], 'b.', ms=3, label="Dew Point")

        ax.set_ylabel("Temperature / Dew Point (°C)")
        ax.set_title(label)
        ax.legend()

        ax.xaxis.set_major_formatter(formatter)
        ax.xaxis.set_major_locator(locator)
        ax.tick_params(axis='x', rotation=45)
        
        ax.fill_between(df["Time"], df["DewPoint"], df["Temperature"],
                where=(df["Temperature"]-df["DewPoint"] < 3),
                color="orange", alpha=0.2)

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.2)

        filename = make_plot_filename(f"{label}_Temp_DewPoint", start_date, end_date)
        save_path = os.path.join(OUTPUT_DIR, filename)

        fig.savefig(save_path, dpi=300)
        print(f"Saved: {save_path}")

        output_figs.append(fig)


    # ---- Pressure difference plots ----
    pairs = [
        ("Room A","Chase area"),
        ("Room B","Chase area"),
        ("Room C","Chase area"),
        ("Room D","Chase area"),
        ("Chase area","Lobby")
    ]

    for room, ref in pairs:

        if room not in pi_data or ref not in pi_data:
            continue

        df_delta = pressure_diff(pi_data[room], pi_data[ref])

        fig, ax = plt.subplots(figsize=(10,5))

        ax.plot(df_delta["Time"], df_delta["DeltaP"], 'b.', ms=3)

        ax.axhline(0, linestyle="--")

        ax.set_ylabel("ΔP (inH2O)")
        ax.set_title(f"{room} → {ref}")

        ax.xaxis.set_major_formatter(formatter)
        ax.xaxis.set_major_locator(locator)
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.2)

        filename = make_plot_filename(f"{room}_to_{ref}_PressureDiff", start_date, end_date)
        save_path = os.path.join(OUTPUT_DIR, filename)

        fig.savefig(save_path, dpi=300)
        print(f"Saved: {save_path}")

        output_figs.append(fig)

    return output_figs

if __name__ == "__main__":
    whats_the_weather(start_date, end_date)