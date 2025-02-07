#!/bin/bash
export PATH=$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/games:/usr/games
echo $PATH
echo "Hello world!"
python3 test_sensor_data.py
echo "finished this data run woohoo!"