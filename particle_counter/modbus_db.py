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

def read_particle_data(client):
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
    
    finally:
        client.close()

def load_db_config(path="/home/HGC_DB_postgres/dbase_info/conn.yaml"):
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config["postgres"]

async def connect_to_db():
    config = load_db_config("/home/HGC_DB_postgres/dbase_info/conn.yaml")
    conn = await asyncpg.connect(
        host=config["db_hostname"],
        database=config["dbname"],
        #user=replace, --I need to get this info from Valdis
        #password=replace,
        port=config["port"]
    )
    return conn

# Async function to listen for database updates
async def listen_to_notifications():
    conn = await asyncpg.connect(
        host=config["db_hostname"],
        database=config["dbname"],
        #user=replace,
        #password=replace,
        port=config["port"]
    )
    
    await conn.add_listener('new_test_data', handle_notification)
    print("Listening for PostgreSQL notifications...")

    try:
        while True:
            await asyncio.sleep(60)  # Keep alive
    finally:
        await conn.close()

# When notified, take a measurement and insert into another table
async def handle_notification(conn, pid, channel, payload):
    print(f"Received trigger: {payload}")
    data = read_particle_data()
    if data is None:
        print("Measurement failed or incomplete.")
        return

    await conn.execute('''
        INSERT INTO counter_info(data)
        VALUES($1)
    ''', json.dumps(data))

    print("Logged full measurement dictionary to DB.")

if __name__ == "__main__":
    asyncio.run(listen_to_notifications())