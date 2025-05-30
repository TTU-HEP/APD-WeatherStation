from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException
from pymodbus.exceptions import ModbusIOException

import pymodbus
import struct
from datetime import datetime
import json
import time
import os
import re

# Connection settings
DEVICE_IP = "129.118.107.203"
DEVICE_PORT = 502

REGISTER_temp = 9079
REGISTER_rh = 9080
REGISTER_bp = 9081

# File to log the data
#LOG_FILE = "/home/daq2-admin/APD-WeatherStation/particle_counter/data_files/cron_job_particle_log.json"
LOG_DIR = "/home/daq2-admin/APD-WeatherStation/particle_counter/data_files"
LOG_BASE_NAME = "counter_data_file"
LOG_EXTENSION = ".json"
MAX_ENTRIES_PER_FILE = 1000

def read_particle_data(client):
    #temp and rh info
    result_temp = client.read_holding_registers(REGISTER_temp)
    result_rh = client.read_holding_registers(REGISTER_rh)
    result_bp = client.read_holding_registers(REGISTER_bp, count=2)

    if result_temp.isError():
        print(f"Error reading registers at {REGISTER_temp}: {result}")
        return None

    if result_rh.isError():
        print(f"Error reading registers at {REGISTER_rh}: {result}")
        return None

    if result_bp.isError():
        print(f"Error reading registers at {REGISTER_bp}: {result}")
        return None

    # Read the raw values for temperature and RH
    temp_raw = result_temp.registers[0]
    rh_raw = result_rh.registers[0]

    # Convert the raw values to meaningful measurements
    temp = temp_raw / 10.0   # Adjust scaling factors as necessary
    rh = rh_raw              # Adjust scaling factors as necessary

    decoder_bp = BinaryPayloadDecoder.fromRegisters(
            result_bp.registers,
            byteorder=Endian.BIG,
            wordorder=Endian.LITTLE
        )

    bp  = decoder_bp.decode_32bit_float()

   # Particle size and count info
    CHANNEL_SIZE_BASE = 10100
    DIFF_COUNT_BASE = 10700

    REGISTERS_PER_CHANNEL = 2
    NUM_CHANNELS = 6
    
    diff_data = {}
    
    for i in range(NUM_CHANNELS):
        size_addr = CHANNEL_SIZE_BASE + (i * REGISTERS_PER_CHANNEL)
        diff_addr = DIFF_COUNT_BASE + (i * REGISTERS_PER_CHANNEL)
    
        result_size = client.read_holding_registers(address=size_addr, count=REGISTERS_PER_CHANNEL)
        time.sleep(0.2)
    
        result_diff = client.read_holding_registers(address=diff_addr, count=REGISTERS_PER_CHANNEL)
        time.sleep(0.2)
        
        if result_size.isError() or result_diff.isError():
            print(f"Error reading particle channel {i}")
            continue
        
        decoder_size = BinaryPayloadDecoder.fromRegisters(
            result_size.registers,
            byteorder=Endian.BIG,
            wordorder=Endian.LITTLE
        )
        
        decoder_diff = BinaryPayloadDecoder.fromRegisters(
            result_diff.registers,
            byteorder=Endian.BIG,
            wordorder=Endian.LITTLE
        )
        
        size_um = decoder_size.decode_32bit_float()
        diff_m3 = decoder_diff.decode_32bit_float()
        
        # Store in dictionary with formatted key
        diff_data[f"{size_um:.2f} um"] = diff_m3
        
    # Verify all 6 channels are present before final dict is made.
    if len(diff_data) < NUM_CHANNELS:
        print("Incomplete data read. Skipping this cycle.")
        return None

    # Final data dictionary
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "temp": temp,
        "RH": rh,
        "BP": bp,
        "diff_counts_m3": diff_data
    }

    print("\n")
    print(f"Timestamp:", datetime.now().strftime("%Y-%m-%d %H:%M:%S") )
    print(f"Temperature: {temp}°C, RH: {rh}%, Barometric Pressure: {bp}")
    for size, count in diff_data.items():
        print(f"Size: {size}, Differential Count/m³: {count}")
    print("\n")

    return data

def get_latest_log_file():
    files = [f for f in os.listdir(LOG_DIR) if f.startswith(LOG_BASE_NAME) and f.endswith(LOG_EXTENSION)]
    
    # Extract numeric part and sort
    numbered_files = []
    for fname in files:
        match = re.match(rf"{LOG_BASE_NAME}(\d+){LOG_EXTENSION}", fname)
        if match:
            numbered_files.append((int(match.group(1)), fname))
    
    if not numbered_files:
        return os.path.join(LOG_DIR, f"{LOG_BASE_NAME}1{LOG_EXTENSION}")

    latest_num, latest_file = max(numbered_files)
    latest_path = os.path.join(LOG_DIR, latest_file)
    
    # Check if it has reached the max entries
    with open(latest_path, "r") as f:
        lines = sum(1 for _ in f)

    if lines >= MAX_ENTRIES_PER_FILE:
        # Start a new file
        new_num = latest_num + 1
        return os.path.join(LOG_DIR, f"{LOG_BASE_NAME}{new_num}{LOG_EXTENSION}")
    else:
        return latest_path

def log_data_to_file(data):
    log_file = get_latest_log_file()
    with open(log_file, "a") as f:
        f.write(json.dumps(data) + "\n")

def run_logging_loop():
    start_time = time.time()
    duration = 59 * 60  # run for 59 minutes
    end_time = start_time + duration

    # Timing parameters
    normal_interval = 600  # 10 minutes
    alert_interval = 60    # 1 minute
    current_interval = normal_interval
    should_exit = False

    # Channel sizes
    channel_keys = ["0.30 um", "0.50 um", "1.00 um", "2.50 um", "5.00 um", "10.00 um"]

    # ISO 6 max values per channel (counts/m³)
    max_vals = [102000, 35200, 8320, 8320, 293, 293]

    # Thresholds for switching to alert mode (50% of ISO max)
    alert_thresholds = [0.5 * val for val in max_vals]
    in_alert_mode = False

    while time.time() < end_time and not should_exit:
        client = None
        try:
            client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT, timeout=5)
            if not client.connect():
                print("Initial connection failed. Retrying in 10 seconds...")
                time.sleep(10)
                continue

            print("Connected to Modbus device.")
            time.sleep(2)

            while time.time() < end_time:
                try:
                    now = time.time()
                    time_left = end_time - now

                    data = read_particle_data(client)
                    if data:
                        diff_counts = data["diff_counts_m3"]
                        monitored_counts = [diff_counts.get(key, 0) for key in channel_keys]

                        # Check for alert condition
                        exceeds_threshold = any(
                            count >= threshold
                            for count, threshold in zip(monitored_counts, alert_thresholds)
                        )

                        if not in_alert_mode and exceeds_threshold:
                            print("Threshold exceeded! Entering alert mode (1-minute logging).")
                            current_interval = alert_interval
                            in_alert_mode = True

                        elif in_alert_mode and all(
                            count < threshold
                            for count, threshold in zip(monitored_counts, alert_thresholds)
                        ):
                            print("All channels below threshold. Returning to normal mode (10-minute logging).")
                            current_interval = normal_interval
                            in_alert_mode = False

                        log_data_to_file(data)

                    # Sleep logic based on remaining time
                    if time_left >= current_interval:
                        time.sleep(current_interval)
                    elif time_left >= alert_interval:
                        print(f"Less than {current_interval} seconds remaining, switching to 1-minute interval.")
                        time.sleep(alert_interval)
                    else:
                        print("Less than 1 minute remaining — exiting early to avoid overlap.")
                        should_exit = True  # signal outer loop to stop
                        break
                
                except (ConnectionResetError, ConnectionException, ModbusIOException) as e:
                    print(f"Connection lost: {e}. Attempting to reconnect...")
                    break  # Exit inner loop to reconnect

        except KeyboardInterrupt:
            print("Logging stopped by user.")
            break

        except Exception as e:
            print(f'Unexpected error while connecting: {e}')
            time.sleep(5)
            continue

        finally:
            if client is not None:
                try:
                    print("Loop closed. Have a nice day.")
                    client.close()
                except:
                    pass
            if should_exit:
                print("Exitting outer loop cleanly.")
                break

if __name__ == "__main__":
    run_logging_loop()
