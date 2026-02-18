#!/bin/bash

#config
REMOTE_HOST = 129.118.107.198
EMAIL_SUBJECT = "Alert: Daq2 computer is inaccessible/powered off"
EMAIL_BODY = "$REMOTE_HOST is unreachable as of $(date)"
RECIPIENT_FILE = "/home/student/recipients.txt"
LOG_FILE = "/home/student/ping_monitor.log"

# ping daq2 (1 packet w/ a 5 second wait)
ping -c 1 -w 5 "REMOTE_HOST" > /dev/null 2&1

if [ $? -ne 0 ]; then
        echo "$(date): $REMOTE_HOST is unreachable. Sending alert..." >> "$LOG_FILE"

        # read recipient emails line by line
        while IFS= read -r email || [ -n "$email" ]; do
                email="$echo "$email" | xargs)"
                if [[ -n "$email" && "$email" != \#" ]]; then
                        echo "$EMAIL_BODY" | mail -s "$EMAIL_SUBJECT" "$email"
                else
                        echo "$(date): skipped invalid email: $email" >> "$LOG_FILE"
                fi
        done < "$RECIPIENT_FILE"
else
        echo "$(date): $REMOTE_HOST is still accessible" >> "$LOG_FILE"
fi
