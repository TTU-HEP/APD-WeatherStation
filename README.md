General scripts for use on raspberry pi weatherstation configs across the APD lab.

WIP!


Crontab entry looks like:

``` 
50 * * * * /bin/bash /path/to/script/test_parallel_pi.sh >> /path/to/log/backup3.log 2>&1
49 * * * * /usr/bin/python3 /path/to/script/plot_weather.py >> /path/to/log/backup4.log 2>&1
```