import csv
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.ticker import MaxNLocator
files=["p129.118.107.205_output_2025052701.csv", "p129.118.107.234_output_2025052701.csv", "p129.118.107.204_output_2025052701.csv", "p129.118.107.233_output_2025052701.csv", "p129.118.107.235_output_2025052701.csv" ,"p129.118.107.232_output_2025052701.csv"]

naming_dict={"p129.118.107.205_output_2025052701.csv": "Pi A", 
"p129.118.107.234_output_2025052701.csv": "Pi B", 
"p129.118.107.204_output_2025052701.csv": "Pi C", 
"p129.118.107.233_output_2025052701.csv": "Pi D", 
"p129.118.107.235_output_2025052701.csv": "Pi E",
"p129.118.107.232_output_2025052701.csv": "Pi F"}

colors = {"p129.118.107.205_output_2025052701.csv": "b", 
"p129.118.107.234_output_2025052701.csv": "r", 
"p129.118.107.204_output_2025052701.csv": "g", 
"p129.118.107.233_output_2025052701.csv": "y", 
"p129.118.107.235_output_2025052701.csv": "c",
"p129.118.107.232_output_2025052701.csv": "m"}


#cut_off_date = pd.to_datetime("2025-05-27 00:00:00")

fig, axs = plt.subplots(1, 3, figsize=(15, 5))

for i in files:
    df = pd.read_csv("/home/daq2-admin/APD-WeatherStation/data_folder/"+i)
    df['Time'] = pd.to_datetime(df['Time'])
    time=df["Time"].to_numpy()
    humidity=df["Humidity"].to_numpy()
    temperature=df["Temperature"].to_numpy()
    pressure=df["Pressure"].to_numpy()
    
    # Apply mask to filter events after the 5th of February
    #mask = time < cut_off_date

    axs[0].scatter(time, humidity, marker='o', s=20, color=colors[i], label=naming_dict[i])
    axs[0].set_xlabel("Time")
    axs[0].set_ylabel("Humidity %%")
    axs[0].set_title("Overlaid plots - Humidity")

    #mask = (temperature >= 0) & (temperature <= 40)
    axs[1].scatter(time, temperature, marker='o', s=20, color=colors[i], label=naming_dict[i])
    axs[1].set_xlabel("Time")
    axs[1].set_ylabel("Temperature C")
    axs[1].set_title("Overlaid plots - Temperature")

    #mask = (pressure >= 890) & (pressure <= 910)
    axs[2].scatter(time, pressure, marker='o', s=20, color=colors[i], label=naming_dict[i])
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

plt.savefig("/home/daq2-admin/APD-WeatherStation/test_overlaid_plots.png")

print("Plots should be finished! (God help us all)")
#print("inside of pressure: ", pressure)

df1 = pd.read_csv("/home/daq2-admin/APD-WeatherStation/data_folder/p129.118.107.235_output_2025052701.csv")
pressure1=df1["Pressure"].to_numpy()
avr_D = np.average(pressure1, axis=None)
print("average pressure from Pi E is ", avr_D, "hPa")

df2 = pd.read_csv("/home/daq2-admin/APD-WeatherStation/data_folder/p129.118.107.232_output_2025052701.csv")
pressure2=df2["Pressure"].to_numpy()
avr_F = np.average(pressure2, axis=None)
print("average pressure from pi F is ", avr_F, "hPa")

diff = avr_D - avr_F
print("The mean difference between Pi E (Chase area) and Pi F (lobby) is ", diff, "hPa")
