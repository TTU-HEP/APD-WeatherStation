This directory has to do with communicating with the particle counter in the clean room. 
Preferrably, this code will not have to move from this computer. 
Moreover, the cronjob running in the background (check with crontab -l) will run the code automatically.
For the time being, plotting is done manually with json_plotting_script.py. 
When you run that script, make sure you give the start time and end tim in the proper format (i.e. YYYY-MM-DD HH:MM:SS). 
You don't have to get the time right down to the second, but at least put the year, month, date, and hour correctly.
To actively monitor the cronjob, go to /cron_logs and use "cat cron_log.txt" to view the most recent readout from the job.
tail -100 cron_log.txt also works if you only want to look at a finite amount of lines.
