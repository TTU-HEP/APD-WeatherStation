import asyncpg
import asyncio
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

async def fetch_data():
    conn = await asyncpg.connect(
        host=config["db_hostname"],
        database=config["dbname"],
        user=config["username"],
        password=config["password"],
        port=config["port"]
    )

    rows = await conn.fetch('''
        SELECT data
        FROM counter_info
        WHERE data IS NOT NULL
        ORDER BY (data->>'timestamp')::timestamp
    ''')

    await conn.close()

     # Convert records to list of dictionaries
    data = [dict(row['data']) for row in rows if row['data'] is not None]
    return data

def plot_data(data):
    timestamps = [datetime.strptime(d["timestamp"], "%Y-%m-%d %H:%M:%S") for d in data]
    temps = [float(d["temp"]) for d in data]
    rhs = [float(d["RH"]) for d in data]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    ax1.set_xlabel("Time")
    ax1.set_ylabel("Temperature (°C)", color="tab:red")
    ax1.plot(timestamps, temps, color="tab:red", label="Temp")
    ax1.tick_params(axis="y", labelcolor="tab:red")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Relative Humidity (%)", color="tab:blue")
    ax2.plot(timestamps, rhs, color="tab:blue", label="RH")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    date_format = DateFormatter("%m-%d %H:%M")
    ax1.xaxis.set_major_formatter(date_format)
    fig.autofmt_xdate()

    plt.title("Temperature and RH from PostgreSQL")
    plt.tight_layout()
    plt.show()

# Run the script
if __name__ == "__main__":
    data = asyncio.run(fetch_data())
    if data:
        plot_data(data)
    else:
        print("No data found.")