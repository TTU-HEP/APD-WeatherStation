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
timestamps = [datetime.fromstrftime(entry["timestamp"]) for entry in data]
temps = [entry["temp"] for entry in data]
rhs = [entry["rh"] for entry in data]

# Extract particle counts per size
particle_counts = {size: [] for size in data[0] if "um" in size}
for entry in data:
    for size in particle_counts:
        particle_counts[size].append(entry[size])

# Plot Temp and RH with dual y-axes
fig, ax1 = plt.subplots()
ax2 = ax1.twinx()

ax1.plot(timestamps, temps, 'b-', label='Temperature (°C)')
ax2.plot(timestamps, rhs, 'r-', label='RH (%)')

ax1.set_xlabel('Time')
ax1.set_ylabel('Temperature (°C)', color='b')
ax2.set_ylabel('Relative Humidity (%)', color='r')

plt.title("Temperature and Relative Humidity Over Time")
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "temp_rh_plot.png"))
plt.show()

# Plot each particle count in a separate figure and save
for size, counts in particle_counts.items():
    plt.figure()
    plt.plot(timestamps, counts, label=f"{size} count/ft³")
    plt.xlabel("Time")
    plt.ylabel("Particle Count (/ft³)")
    plt.title(f"Particle Count for {size}")
    plt.tight_layout()
    filename = f"particle_count_{size.replace(' ', '').replace('um', 'um')}.png"
    plt.savefig(os.path.join(output_dir, filename))
    plt.show()