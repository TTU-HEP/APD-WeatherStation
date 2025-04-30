from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

import pymodbus
#print(pymodbus.__version__ )

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
    rh = rh_raw       # Adjust scaling factors as necessary

    # Prepare the data dictionary with timestamp and processed values
    data = {
        "timestamp": datetime.now().isoformat(),
        "temp": temp,
        "rh": rh
    }

    # Optionally, print the data for debugging
    print(f"Temperature: {temp}°C, RH: {rh}%")

    return data

def explore_channel_sizes(client):
    BASE_ADDRESS = 10100  # Starting register address for channel sizes
    NUM_CHANNELS = 200  
    REGISTERS_PER_CHANNEL = 2  # Each float is 32 bits = 2 registers (2 x 16 bits)

    for i in range(6):
        address = BASE_ADDRESS + (i * REGISTERS_PER_CHANNEL)
        result = client.read_holding_registers(address=address,count=REGISTERS_PER_CHANNEL)
       
        if result.isError():
            print(f"Error reading channel {i} at address {address}: {result}")
            continue
    
        print(f"raw registers from address {address}: {result.registers}")
        #print(f"type of regisiters: {type(result.registers)}, contents: {result.registers}")

        # Decode using correct byte and word order
        decoder = BinaryPayloadDecoder.fromRegisters(
            result.registers,
            byteorder=Endian.BIG,
            wordorder=Endian.LITTLE
        )
        
        channel_size_um = decoder.decode_32bit_float()
        print("channel size (um):", channel_size_um)

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
            explore_channel_sizes(client) #Comment out & remove function when applicable.
            client.close()
    else:
        print("Failed to connect to device.")
