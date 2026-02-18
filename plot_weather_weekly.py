import os
import glob
import csv
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.ticker import MaxNLocator
from collections import defaultdict
from datetime import datetime

OUTPUT_DIR = "/home/daq2-admin/APD-WeatherStation/weekly_plots/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

def whats_the_weather(start_date, end_date):
    directory = "/home/daq2-admin/APD-WeatherStation/data_folder/"
    prefixes = {
        "p129.118.107.205": "Room D",
        "p129.118.107.234": "Room B",
        "p129.118.107.204": "Room C",
        "p129.118.107.233": "Room A",
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
    for prefix, files in grouped_files.items():
        label = prefixes.get(prefix, prefix)
        print(f"\nProcessing {label}")

        dfs = []
        for file_path in sorted(files):
            df = pd.read_csv(file_path)

            # Convert Time column properly
            df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
            df = df.dropna(subset=["Time"])

            dfs.append(df)

        if not dfs:
            continue

        df = pd.concat(dfs, ignore_index=True)

        time = df["Time"].to_numpy()
        humidity = df["Humidity"].to_numpy()
        temperature = df["Temperature"].to_numpy()
        pressure = df["Pressure"].to_numpy()

        fig, axs = plt.subplots(1, 3, figsize=(15, 5))

        # ---- Humidity ----
        mask = (humidity >= 5) & (humidity <= 60)
        axs[0].plot(time[mask], humidity[mask], 'go', ms=3)
        axs[0].set_xlabel("Time")
        axs[0].set_ylabel("Humidity [%]")
        axs[0].set_title(label)

        # ---- Temperature ----
        mask = (temperature >= 0) & (temperature <= 40)
        axs[1].plot(time[mask], temperature[mask], 'ro', ms=3)
        axs[1].set_xlabel("Time")
        axs[1].set_ylabel("Temperature [C]")
        axs[1].set_title(label)

        # ---- Pressure ----
        mask = (pressure >= 890) & (pressure <= 910)
        axs[2].plot(time[mask], pressure[mask], 'bo', ms=3)
        axs[2].set_xlabel("Time")
        axs[2].set_ylabel("Pressure")
        axs[2].set_title(label)

        # ---- Axis formatting ----
        for ax in axs:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
            ax.tick_params(axis='x', rotation=30)

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.2)

        filename = make_plot_filename(label, start_date, end_date)
        save_path = os.path.join(OUTPUT_DIR, filename)

        fig.savefig(save_path, dpi=300)
        print(f"Saved: {save_path}")

        output_figs.append(fig)

    return output_figs

if __name__ == "__main__":
    whats_the_weather(start_date, end_date)