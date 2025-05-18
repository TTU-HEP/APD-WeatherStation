from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException

import pymodbus
import struct
from datetime import datetime
import json
import yaml
import time
import asyncio
import asyncpg

# Connection settings
DEVICE_IP = "129.118.107.203"
DEVICE_PORT = 502

def read_particle_data():
    client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT)

    if not client.connect():
        print("Could not connect to device.")
        return None
    try:
        #temp and rh info
        REGISTER_temp = 9079
        REGISTER_rh = 9080
        REGISTER_bp = 9081
        
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
            result_diff = client.read_holding_registers(address=diff_addr, count=REGISTERS_PER_CHANNEL)

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

         # Sanity check: no nulls
        if any(c is None for c in diff_counts) or temperature is None or humidity is None:
            print("One or more sensor values were None.")
            return None
            
        # Final data dictionary
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temp": temp,
            "RH": rh,
            "BP": bp,
            "diff_counts_m3": diff_data
    }
    
    finally:
        client.close()

def load_db_config(path):
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config["postgres"]

async def connect_to_db():
    config = load_db_config("/home/HGC_DB_postgres/dbase_info/conn1.yaml")
    conn = await asyncpg.connect(
        host=config["db_hostname"],
        database=config["dbname"],
        user=config["username"],
        password=config["password"],
        port=config["port"]
    )
    return conn

config = load_db_config("/home/HGC_DB_postgres/dbase_info/conn1.yaml")

async def listen_to_notifications():
    conn = await asyncpg.connect(
        host=config["db_hostname"],
        database=config["dbname"],
        user=config["username"],
        password=config["password"],
        port=config["port"]
    )
    await conn.add_listener('new_test_data', handle_notification)
    print("Listening for PostgreSQL notifications...")
    try:
        while True:
            await asyncio.sleep(60)
    finally:
        await conn.close()

# When notified, take a measurement and insert into another table
async def handle_notification(conn, pid, channel, payload):
    try:
        print(f"Received trigger: {payload}")
        
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, read_particle_data)

        # Base check
        if not data or not isinstance(data, dict):
            print("Measurement failed or returned non-dict. Skipping insert.")
            return

        # Ensure expected keys are present and non-null
        required_keys = {"diff_counts_m3", "temp", "rh"}
        if not required_keys.issubset(data.keys()):
            print(f"Missing keys in data: {required_keys - data.keys()}")
            return

        # Check for nulls in values
        if (
            data["diff_counts_m3"] is None or
            not isinstance(data["diff_counts_m3"], list) or
            any(v is None for v in data["diff_counts_m3"]) or
            data["temp"] is None or
            data["rh"] is None or
            data["BP"] is None
        ):
            print("One or more data fields are None. Skipping insert.")
            return

        # Debugging output
        print("Prepared data for insert:")
        print(json.dumps(data, indent=2))

        await conn.execute('''
            INSERT INTO counter_info(data)
            VALUES($1)
        ''', json.dumps(data))

        print("Logged full measurement dictionary to DB.")
    except Exception as e:
        print(f"Error in handle_notification: {e}")

if __name__ == "__main__":
    asyncio.run(listen_to_notifications())
