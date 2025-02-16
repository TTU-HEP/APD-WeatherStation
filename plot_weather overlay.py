import csv
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.ticker import MaxNLocator
files=["10.191.12.6-output.csv", "10.191.12.130-output.csv", "10.191.12.4-output.csv", "10.191.12.129-output.csv", "10.191.12.132-output.csv" ,"10.191.12.3-output.csv"]

naming_dict={"10.191.12.6-output.csv": "Pi A", 
"10.191.12.130-output.csv": "Pi B", 
"10.191.12.4-output.csv": "Pi C", 
"10.191.12.129-output.csv": "Pi D", 
"10.191.12.132-output.csv": "Pi E",
"10.191.12.3-output.csv": "Pi F"}

colors = {"10.191.12.6-output.csv": "b", 
"10.191.12.130-output.csv": "r", 
"10.191.12.4-output.csv": "g", 
"10.191.12.129-output.csv": "y", 
"10.191.12.132-output.csv": "c",
"10.191.12.3-output.csv": "m"}


cut_off_date = pd.to_datetime("2025-02-04 00:00:00")

fig, axs = plt.subplots(1, 3, figsize=(15, 5))

for i in files:
    df = pd.read_csv("/home/gvetters/APD-WeatherStation/data_folder/"+i)
    df['Time'] = pd.to_datetime(df['Time'])
    time=df["Time"].to_numpy()
    humidity=df["Humidity"].to_numpy()
    temperature=df["Temperature"].to_numpy()
    pressure=df["Pressure"].to_numpy()
    
    # Apply mask to filter events after the 5th of February
    mask = time < cut_off_date

    #mask = (humidity >= 10) & (humidity <= 60)
    axs[0].scatter(time[mask], humidity[mask], marker='o', s=20, color=colors[i], label=naming_dict[i])
    axs[0].set_xlabel("Time")
    axs[0].set_ylabel("Humidity %%")
    axs[0].set_title("Overlaid plots - Humidity")

    #mask = (temperature >= 0) & (temperature <= 40)
    axs[1].scatter(time[mask], temperature[mask], marker='o', s=20, color=colors[i], label=naming_dict[i])
    axs[1].set_xlabel("Time")
    axs[1].set_ylabel("Temperature C")
    axs[1].set_title("Overlaid plots - Temperature")

    #mask = (pressure >= 890) & (pressure <= 910)
    axs[2].scatter(time[mask], pressure[mask], marker='o', s=20, color=colors[i], label=naming_dict[i])
    #axs[2].set_ylim(875,925)
    axs[2].set_xlabel("Time")
    axs[2].set_ylabel("Pressure [unit]")
    axs[2].set_title("Overlaid plots - Pressure")

    axs[0].xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', nbins=7))
    axs[1].xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', nbins=7))
    axs[2].xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', nbins=7))
    ticks = axs[0].get_xticklabels()
    for tick in ticks:
        tick.set_horizontalalignment('right')
    # Set horizontal alignment of x-tick labels to 'center'
    ticks = axs[1].get_xticklabels()
    for tick in ticks:
        tick.set_horizontalalignment('right')
    ticks = axs[2].get_xticklabels()
    for tick in ticks:
        tick.set_horizontalalignment('right')

  
    #plt.xticks(rotation=45)
    for ax in axs:
        ax.tick_params(axis='x', rotation=30)
        ax.legend(loc="best", fontsize=8)
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m-%d %H:%M:%S'))

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)
    
plt.savefig("/home/gvetters/APD-WeatherStation/image_dir/overlaid_plots.pdf")
plt.savefig("/home/gvetters/APD-WeatherStation/image_dir/overlaid_plots.png")

print("Plots should be finished! (God help us all)")
