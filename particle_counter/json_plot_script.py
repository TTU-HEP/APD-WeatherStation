import json
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from datetime import datetime
import os

# Define output directory for plots
output_dir = "/home/daq2-admin/APD-WeatherStation/particle_counter/plots"
os.makedirs(output_dir, exist_ok=True)

timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
filename_plot1 = f"temp_rh_{timestamp_str}.png"
filename_plot2 = f"particle_cts_combined_{timestamp_str}.png" 


# Load data from JSON file
with open("/home/daq2-admin/APD-WeatherStation/particle_counter/data_files/cron_job_particle_log.json", "r") as file:
    lines = file.readlines()
    data = [json.loads(line) for line in lines]

start_str = input("Enter start datetime in this format: (YYYY-MM-DD HH:MM:SS ): ")
end_str = input("Enter end datetime in this format: (YYYY-MM-DD HH:MM:SS): ")

start_date = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S').date()
end_date = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S').date()


# Extract timestamps, temp, and RH
filtered_data = []

for entry in data:
    timestamp_str = entry["timestamp"]
    if isinstance(timestamp_str, str):
        entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").date()
        if start_date <= entry_date <= end_date:
            filtered_data.append(entry)

timestamps = [datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S") for entry in filtered_data]
temps = [entry["temp"] for entry in filtered_data]
RHs = [entry["RH"] for entry in filtered_data]

avr_temp = sum(temps)/len(temps)
avr_RH = sum(RHs)/len(RHs)

# ---- Plot Temp and RH with dual y-axes ----
fig, ax1 = plt.subplots()
ax2 = ax1.twinx()

ax1.plot(timestamps, temps, color='b', marker='o', ms=3.0, label='Temperature (°C)')
ax2.plot(timestamps, RHs, color='r', marker='o', ms=3.0, label='RH (%)')

ax1.set_xlabel('Time')
ax1.set_ylabel('Temperature (°C)')
ax2.set_ylabel('Relative Humidity (%)')

#Format time properly
date_format = DateFormatter("%Y-%m-%d %H:%M:%S")
ax1.xaxis.set_major_formatter(date_format)

text_str = f"Average temp: {avr_temp:.2f}°C/nAverage RH: {avr_RH:.2f}%"
ax1.text(0.01, 0.95, text_str, transform=ax1.transAxes,
        fontsize=10, verticalalignment='top',
        bbox=dict(facecolor='white', alpha=0.6, edgecolor='gray'))

plt.title("Temperature and Relative Humidity Over Time")
fig.autofmt_xdate(rotation=45)
#plt.xticks(fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, filename_plot1))
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
fig, axs = plt.subplots(3, 2, figsize=(15, 8), sharex=True)
axs = axs.flatten()

expected_channels = ["0.30 um", "0.50 um", "1.00 um", "2.50 um", "5.00 um", "10.00 um"]

#for i, (channel, data_dict) in enumerate(channel_data.items()):
for i, channel in enumerate(expected_channels):
    if channel in channel_data:
        axs[i].plot(channel_data[channel]["timestamps"], channel_data[channel]["diff_counts_m3"], marker='o', ms=3.0, label=channel)
        axs[i].set_title(channel)
        axs[i].set_xlabel("time")
        axs[i].set_ylabel("count/m3")
        axs[i].xaxis.set_major_formatter(date_format)
        axs[i].tick_params(axis='x', rotation=45, labelsize=6, labelbottom=True)

fig.suptitle("Differential counts per Cubic Meter for each Channel of Interest", fontsize=16)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, filename_plot2))
plt.show()

plt.close()
print("Plots were successfully generated. Make sure to check them.")
