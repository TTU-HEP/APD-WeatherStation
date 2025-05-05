from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian
import pymodbus.exceptions

import pymodbus
import struct
from datetime import datetime
import json
import time

# Connection settings
DEVICE_IP = "129.118.107.203"
DEVICE_PORT = 502

REGISTER_temp = 9079
REGISTER_rh = 9080 

# File to log the data
LOG_FILE = "particle_log.json"

def read_particle_data(client):
    #temp and rh info
    result_temp = client.read_holding_registers(REGISTER_temp)
    result_rh = client.read_holding_registers(REGISTER_rh)
    
    if result_temp.isError():
        print(f"Error reading registers at {REGISTER_temp}: {result}")
        return None

    if result_rh.isError():
        print(f"Error reading registers at {REGISTER_rh}: {result}")
        return None

    # Read the raw values for temperature and RH
    temp_raw = result_temp.registers[0]
    rh_raw = result_rh.registers[0]

    # Convert the raw values to meaningful measurements
    temp = temp_raw / 10.0   # Adjust scaling factors as necessary
    rh = rh_raw              # Adjust scaling factors as necessary

   # Particle size and count info
    CHANNEL_SIZE_BASE = 10100
    DIFF_COUNT_BASE = 10700

    REGISTERS_PER_CHANNEL = 2
    NUM_CHANNELS = 6

    particle_data = {}

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
            result_count.registers,
            byteorder=Endian.BIG,
            wordorder=Endian.LITTLE
        )

        size_um = decoder_size.decode_32bit_float()
        diff_m3 = decoder_count.decode_32bit_float()

        # Store in dictionary with formatted key
        diff_data[f"{size_um:.2f} um"] = count_m3

    # Final data dictionary
    data = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "temp": temp,
        "RH": rh,
        "diff_counts_m3": diff_data
    }

    print(f"Temperature: {temp}°C, RH: {rh}%")

    for size, count in diff_data.items():
        print(f"Size: {size}, Differential Count/m³: {count}")

    return data

def log_data_to_file(data):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

def run_logging_loop():
    while True:
        try:
            client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT)
            if not client.connect():
                print("Initial connection failed. Retrying in 5 seconds...")
                time.sleep(5)
                continue

            print("Connected to Modbus device.")
            while True:
                try:
                    data = read_particle_data(client)
                    if data:
                        log_data_to_file(data)
                    time.sleep(60)
                except (ConnectionResetError, ConnectionException) as e:
                    print(f"Connection lost: {e}. Attempting to reconnect...")
                    client.close()
                    time.sleep(2)
                    break  # Exit inner loop to reconnect

        except KeyboardInterrupt:
            print("Logging stopped by user.")
            try:
                client.close()
            except:
                pass
            break  # Exit the outer loop cleanly

if __name__ == "__main__":
    run_logging_loop()