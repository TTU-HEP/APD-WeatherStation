#!/bin/bash
export PATH=$PATH:"/home/gvetters/anaconda3/bin:/home/gvetters/anaconda3/condabin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/usr/lib/wsl/lib:/mnt/c/Program Files/WindowsApps/MicrosoftCorporationII.WindowsSubsystemForLinux_2.4.11.0_x64__8wekyb3d8bbwe:/mnt/c/Program Files/Git/cmd:/mnt/c/Program Files/Git/bin"
export PYTHONPATH=$PYTHONPATH:"/usr/local/lib/python3.7/dist-packages"
# List of Raspberry Pi IP addresses (or hostnames)
PI_ADDRESSES=("10.191.12.6" "10.191.12.130" "10.191.12.4" "10.191.12.129" "10.191.12.132" "10.191.12.3") #"10.191.12.5","10.191.12.132","10.191.12.1",

# The remote script you want to run on each Raspberry Pi
REMOTE_SCRIPT_PATH="collect_sensor_data.sh"

# The output file to fetch from each Raspberry Pi
OUTPUT_FILE="test_output.csv"

# The directory on your local machine to store the results
#LOCAL_DIR="/Users/sloks/Public/"
LOCAL_DIR="/home/gvetters/APD-WeatherStation/data_folder"

# Ensure the local directory exists
# mkdir -p "$LOCAL_DIR""
pwd
# Function to SSH and SCP the output from a single Raspberry Pi
process_pi() {
    local pi_address="$1"
    echo "Running script on $pi_address"
    # Run the remote script and output to a file
    #ssh pi@$pi_address "/bin/bash collect_sensor_data.sh"
    parallel ssh pi@{} 'PYTHONPATH=/usr/local/lib/python3.7/dist-packages python3 '/home/pi/test_sensor_data.py ::: $PI_ADDRESSES
    echo $pi_address
    # SCP the output file back to the original machine
    echo "$LOCAL_DIR"
    #scp pi@$pi_address:/home/pi/test_output.csv "/Users/sloks/Public/$pi_address-output.csv"
    scp pi@$pi_address:/home/pi/test_output.csv "/home/gvetters/APD-WeatherStation/data_folder/$pi_address-output.csv"
    echo "sillygoose"
    # Optional: Clean up the output file on the Raspberry Pi after transfer
    # ssh pi@"$pi_address" "rm ~/$OUTPUT_FILE"
}

export -f process_pi  # Export the function to be used by parallel

# Use parallel to run the SSH/SCP commands simultaneously
parallel -v process_pi ::: "${PI_ADDRESSES[@]}"

echo "All tasks are complete. Output files have been saved to $LOCAL_DIR"

