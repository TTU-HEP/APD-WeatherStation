from pymodbus.client import ModbusTcpClient
import struct
from datetime import datetime
import json
import time

# Connection settings
DEVICE_IP = "129.118.107.203"
DEVICE_PORT = 502
UNIT_ID = 247

REGISTER_temp = 9079
REGISTER_rh = 9080 

# File to log the data
LOG_FILE = "particle_log.json"

def read_particle_data(client):
    #Make sure to have a new statement for each value grabbed. Try to avoid errors.
    result_temp = client.read_holding_registers(REGISTER_temp) #result_temp = client.read_holding_registers(REGISTER_temp, 1, unit=UNIT_ID)

    result_rh = client.read_holding_registers(REGISTER_rh) #result_rh = client.read_holding_registers(REGISTER_rh, 1, unit=UNIT_ID)
    
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
    rh = rh_raw      # Adjust scaling factors as necessary

    # Prepare the data dictionary with timestamp and processed values
    data = {
        "timestamp": datetime.now().isoformat(),
        "temp": temp,
        "rh": rh
    }

    # Optionally, print the data for debugging
    print(f"Temperature: {temp}°C, RH: {rh}%")

    return data

def log_data_to_file(data):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

if __name__ == "__main__":
    client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT)

    if client.connect():
        print("Connected to Modbus device.")
        try:
            while True:
                data = read_particle_data(client)
                if data:
                    print(f"Logged: {data}")
                    log_data_to_file(data)
                time.sleep(5)
        except KeyboardInterrupt:
            print("Logging stopped by user.")
        finally:
            client.close()
    else:
        print("Failed to connect to device.")
