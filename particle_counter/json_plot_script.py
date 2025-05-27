import json
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from datetime import timedelta
from datetime import datetime
import os
import re

# Define output directory for plots
log_dir = "/home/daq2-admin/APD-WeatherStation/particle_counter/data_files"
output_dir = "/home/daq2-admin/APD-WeatherStation/particle_counter/plots"
os.makedirs(output_dir, exist_ok=True)

timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
filename_plot1 = f"temp_rh_{timestamp_str}.png"
filename_plot2 = f"bp_{timestamp_str}.png"
filename_plot3 = f"particle_cts_combined_{timestamp_str}.png"


# Load data from JSON file
with open("/home/daq2-admin/APD-WeatherStation/particle_counter/data_files/cron_job_particle_log.json", "r") as file:
    lines = file.readlines()
    data = [json.loads(line) for line in lines]
    
while True:
    start_str = input("Enter start datetime in this format: (YYYY-MM-DD HH:MM:SS ): ")
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
        break
    except ValueError:
        print("start datetime is incorrect. Please try again.")

while True:
    end_str = input("Enter end datetime in this format: (YYYY-MM-DD HH:MM:SS): ")
    try:
        end_date = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
        break
    except ValueError:
        print("End datetime is incorrect. Please try again.")

# Helper to identify relevant log files
def get_all_log_files(directory):
    return sorted([
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if re.match(r'counter_data_file\d+\.json$', f)
    ])

# Extract timestamps, temp, and RH
filtered_data = []

for file_path in get_all_log_files(log_dir):
    with open(file_path, "r") as file:
        for line in file:
            try:
                entry = json.loads(line)
                timestamp = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
                if start_date <= timestamp <= end_date:
                    filtered_data.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # Skip malformed or incomplete lines

timestamps = [datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S") for entry in filtered_data]
temps = [entry["temp"] for entry in filtered_data]
RHs = [entry["RH"] for entry in filtered_data]
BPs = [entry["BP"] for entry in filtered_data]

avr_temp = sum(temps)/len(temps)
avr_RH = sum(RHs)/len(RHs)
avr_BP = sum(BPs)/len(BPs)

def segment_data(timestamps, values, max_gap=timedelta(hours=(44/60))):
    """Split data into segments where time difference between points is <= max_gap."""
    segments = []
    seg_times = [timestamps[0]]
    seg_values = [values[0]]
    for i in range(1, len(timestamps)):
        if timestamps[i] - timestamps[i - 1] > max_gap:
            segments.append((seg_times, seg_values))
            seg_times = []
            seg_values = []
        seg_times.append(timestamps[i])
        seg_values.append(values[i])
    if seg_times:
        segments.append((seg_times, seg_values))
    return segments

# ---- Plot Temp and RH with dual y-axes ----
fig, ax1 = plt.subplots(figsize=(12,6))
ax2 = ax1.twinx()

temp_line = None
rh_line = None

for seg_times, seg_vals in segment_data(timestamps, temps):
    temp_line, = ax1.plot(seg_times, seg_vals, color='b', marker='o', ms=3.0)
for seg_times, seg_vals in segment_data(timestamps, RHs):
    rh_line, = ax2.plot(seg_times, seg_vals, color='r', marker='o', ms=3.0)

label1 = f"Temperature (Average: {avr_temp:.2f}°C)"
label2 = f"RH (Average: {avr_RH:.2f}%)"

lines = [temp_line, rh_line]
labels = [label1, label2]
fig.legend(lines, labels, loc="upper right", frameon=True, framealpha=0.9 )

ax1.set_xlabel('Time')
ax1.set_ylabel('Temperature (°C)')
ax2.set_ylabel('Relative Humidity (%)')

#Format time properly
date_format = DateFormatter("%Y-%m-%d %H:%M:%S")
ax1.xaxis.set_major_formatter(date_format)

plt.title("Temperature and Relative Humidity Over Time")
fig.autofmt_xdate(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(output_dir + '/rh_temp', filename_plot1))
plt.show()

# ---- Plot barometric pressure wrt time ----
fig, ax = plt.subplots(figsize=(12,6))

for seg_times, seg_vals in segment_data(timestamps, BPs):
    bp_line, = ax.plot(seg_times, seg_vals, color='g', marker='o', ms=3.0)

label = f"Average BP: {avr_BP:.2f} kPa"

fig.legend([bp_line], [label], loc="upper right", frameon=True, framealpha=0.9 )

ax.set_xlabel('Time')
ax.set_ylabel('Abs Barometric Pressure (kPa)')
ax.xaxis.set_major_formatter(date_format)

plt.title("Abs Barometric Pressure Over Time")
fig.autofmt_xdate(rotation=45)
plt.savefig(os.path.join(output_dir + '/BP', filename_plot2))
plt.show()

# ---- Extract particle counts per channel ----
channel_sizes = sorted({key for entry in filtered_data if "diff_counts_m3" in entry for key in entry["diff_counts_m3"]})

channel_data = {channel: {"timestamps": [], "diff_counts_m3": []} for channel in channel_sizes}

# Group particle count data per channel
for entry in filtered_data:
    timestamp = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
    if "diff_counts_m3" in entry:
        for channel,count in entry["diff_counts_m3"].items():
            channel_data[channel]["timestamps"].append(timestamp)
            channel_data[channel]["diff_counts_m3"].append(count)


# ---- Plot all particle channels as subplots in one figure ----
max_vals = [102000, 35200, 8320, 8320, 293, 293]
fig, axs = plt.subplots(3, 2, figsize=(15, 8), sharex=True)
axs = axs.flatten()

expected_channels = ["0.30 um", "0.50 um", "1.00 um", "2.50 um", "5.00 um", "10.00 um"]

#for i, (channel, data_dict) in enumerate(channel_data.items()):
for i, channel in enumerate(expected_channels):
    if channel in channel_data:
        ts = channel_data[channel]["timestamps"]
        vals = channel_data[channel]["diff_counts_m3"]
        for seg_times, seg_vals in segment_data(ts, vals):
            axs[i].plot(seg_times, seg_vals, marker='o', ms=3.0) # label=channel
        axs[i].axhline(y=max_vals[i], color='r', linestyle='--')
        axs[i].text(
            ts[0],                          # x-coordinate (start of time axis)
            max_vals[i] * 0.9,              # y-coordinate (just above the line)
            f"ISO 6 max: {max_vals[i]} ct/m3 ",
            color='r', fontsize=8
            )
        axs[i].set_title(channel)
        axs[i].set_xlabel("time")
        axs[i].set_ylabel("count/m3")
        axs[i].xaxis.set_major_formatter(date_format)
        axs[i].tick_params(axis='x', rotation=45, labelsize=6, labelbottom=True)

fig.suptitle("Differential counts per Cubic Meter for each Channel of Interest", fontsize=16)
plt.tight_layout()
plt.savefig(os.path.join(output_dir + '/combined_counts', filename_plot3))
plt.show()

plt.close()
print("Plots were successfully generated. Make sure to check them.")
