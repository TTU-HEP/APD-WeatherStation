import time
import board # type: ignore
import busio # type: ignore
import adafruit_bme280 # type: ignore
import matplotlib.pyplot as plt # type: ignore
import csv
from datetime import datetime

# Initialize I2C
time.sleep(10)
i2c = busio.I2C(board.SCL, board.SDA)
# Initialize the sensor
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)
# Lists to store data
timestamps = []
temperatures = []
humidities = []
pressures = []
# Duration and interval for data collection
duration = 3480 # Collect data for 58 min (3480 seconds) (adjust as needed)
interval = 15   # Collect data every 15 seconds
now = datetime.now()
date_hour_str = now.strftime("%Y%m%d%H")
csv_file = "test_output_"+date_hour_str+".csv"
start_time = time.time()
print("Collecting data...")

#check to see if csv file exists and has headers
try:
    with open(csv_file, mode='r', newline='', encoding='utf-8'):
        pass
except FileNotFoundError:
    # If the file doesn't exist, create it and add headers
    with open(csv_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Time', 'Temperature', 'Humidity', 'Pressure'])

while time.time() - start_time < duration:
    current_time = time.time() - start_time  # Relative time
    timestamps.append(current_time)
    temperatures.append(bme280.temperature)
    humidities.append(bme280.humidity)
    pressures.append(bme280.pressure)
    with open(csv_file, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        now=datetime.now()
        timestamp=now.strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp,bme280.temperature,bme280.humidity,bme280.pressure])
    print(f"Time: {current_time:.1f}s, Temp: {bme280.temperature:.4g}°C, Humidity: {bme280.humidity:.4g}%, Pressure: {bme280.pressure:.4g} hPa")
    time.sleep(interval)
# Plot results
plt.figure(figsize=(10, 6))
plt.subplot(3, 1, 1)
plt.plot(timestamps, temperatures, marker='o', linestyle='-')
plt.xlabel("Time (s)")
plt.ylabel("Temperature (°C)")
plt.title("Time vs Temperature")
plt.subplot(3, 1, 2)
plt.plot(timestamps, humidities, marker='o', linestyle='-', color='green')
plt.xlabel("Time (s)")
plt.ylabel("Humidity (%)")
plt.title("Time vs Humidity")
plt.subplot(3, 1, 3)
plt.plot(timestamps, pressures, marker='o', linestyle='-', color='red')
plt.xlabel("Time (s)")
plt.ylabel("Pressure (hPa)")
plt.title("Time vs Pressure")
plt.tight_layout()
plt.show()
plt.savefig("output.png") # type: ignore
