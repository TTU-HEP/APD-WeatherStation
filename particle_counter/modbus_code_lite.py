#Note: this code is meant to (hopefully) be imported into postgres_tools.py in the hopes particle count would be pushed to DB.

def read_particle_counts():

    from pymodbus.client import ModbusTcpClient
    from pymodbus.payload import BinaryPayloadDecoder   
    from pymodbus.constants import Endian
    from pymodbus.exceptions import ConnectionException

    import pymodbus
    import struct
    from datetime import datetime
    import json
    import time

    # Connection settings
    DEVICE_IP = "129.118.107.203"
    DEVICE_PORT = 502
    client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT)

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

         # Final data dictionary
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "diff_counts_m3": diff_data
    }

    return data