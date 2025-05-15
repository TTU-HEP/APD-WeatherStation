#!/bin/bash
export PATH=$PATH:"/home/daq2-admin/root/bin:/opt/oracle/instantclient:/home/daq2-admin/.local/bin:/home/daq2-admin/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/var/lib/snapd/snap/bin"
export PYTHONPATH=$PYTHONPATH:"/home/daq2-admin/root/lib"
# List of Raspberry Pi IP addresses (or hostnames)
PI_ADDRESSES=("129.118.107.232" " 129.118.107.205" "129.118.107.234" "129.118.107.204" "129.118.107.233" "129.118.107.235" "129.118.107.232")
# The remote script you want to run on each Raspberry Pi
REMOTE_SCRIPT_PATH="collect_sensor_data.sh"

# The output file to fetch from each Raspberry Pi
OUTPUT_FILE="test_output.csv"

# The directory on your local machine to store the results
#LOCAL_DIR="/Users/sloks/Public/"
LOCAL_DIR="/home/daq2-admin/APD-WeatherStation/data_folder"

# Ensure the local directory exists
# mkdir -p "$LOCAL_DIR""
pwd
# Function to SSH and SCP the output from a single Raspberry Pi
process_pi() {
    local pi_address="$1"
    echo "Running script on $pi_address"
    timestamp=$(date +"%Y%m%d%H")

    # Proper SSH call per Pi
    ssh pi@"$pi_address" 'PYTHONPATH=/usr/local/lib/python3.7/dist-packages python3 /home/pi/test_sensor_data.py'

    echo "Fetching output from $pi_address..."
    scp pi@"$pi_address":"/home/pi/test_output_${timestamp}.csv" \
        "/home/daq2-admin/APD-WeatherStation/data_folder/${pi_address}-output_${timestamp}.csv"

    echo "Finished with $pi_address"
}

export -f process_pi  # Export the function to be used by parallel

# Use parallel to run the SSH/SCP commands simultaneously
parallel -v process_pi ::: "${PI_ADDRESSES[@]}"

echo "All tasks are complete. Output files have been saved to $LOCAL_DIR"

