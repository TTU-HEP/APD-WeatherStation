import json
import matplotlib.pyplot as plt
from datetime import datetime
import os

# Define output directory for plots
output_dir = "plots"
os.makedirs(output_dir, exist_ok=True)

# Load data from JSON file
with open("particle_log_test1.json", "r") as file:
    lines = file.readlines()
    data = [json.loads(line) for line in lines]

# Extract timestamps, temp, and RH
timestamps = [datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S") for entry in data]
temps = [entry["temp"] for entry in data]
rhs = [entry["rh"] for entry in data]

# ---- Plot Temp and RH with dual y-axes ----
fig, ax1 = plt.subplots()
ax2 = ax1.twinx()

ax1.plot(timestamps, temps, 'b-', label='Temperature (°C)')
ax2.plot(timestamps, rhs, 'r-', label='RH (%)')

ax1.set_xlabel('Time')
ax1.set_ylabel('Temperature (°C)', color='b')
ax2.set_ylabel('Relative Humidity (%)', color='r')
plt.title("Temperature and Relative Humidity Over Time")
fig.autofmt_xdate(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "temp_rh_plot.png"))
plt.close()

# ---- Extract particle counts per channel ----
channel_sizes = sorted({key for entry in data if "counts" in entry for key in entry["counts"]})
channel_data = {channel: [] for channel in channel_sizes}

# Group particle count data per channel
for entry in data:
    if "counts" in entry:
        for channel in channel_sizes:
            count = entry["counts"].get(channel)
            if count is not None:
                channel_data[channel].append((datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S"), count))

# ---- Plot all particle channels as subplots in one figure ----
fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True)
axes = axes.flatten()

for idx, channel in enumerate(channel_sizes[:6]):
    times, counts = zip(*channel_data[channel])
    axes[idx].plot(times, counts, marker='o', linestyle='-')
    axes[idx].set_title(f"{channel} particles")
    axes[idx].set_ylabel("Count (/ft³)")
    axes[idx].grid(True)

for ax in axes[-2:]:
    ax.set_xlabel("Time")

fig.suptitle("Differential Particle Counts Over Time", fontsize=16)
fig.autofmt_xdate(rotation=45)
fig.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig(os.path.join(output_dir, "particle_counts_combined.png"))
plt.close()