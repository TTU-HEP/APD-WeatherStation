=================================================================
APD Weather Station — Alarm System README
=================================================================

This directory contains the threshold-monitoring alarm system for
the weather station Pis (temperature, humidity, pressure, and
optionally particle counts). It checks the latest sensor data
against configured limits and emails a summary if anything is out
of range.

This system was built to be reusable by other labs with different
hardware/room setups — everything specific to YOUR lab lives in
config files, not in the Python script itself. You should not need
to edit alarm_email_V2.py directly; edit the config and template
files instead.


-----------------------------------------------------------------
1. FILES IN THIS DIRECTORY
-----------------------------------------------------------------

alarm_email_V2.py
    The alarm script itself. Config-driven — reads everything it
    needs from a YAML config file (see below). Run this via cron
    (or manually) on a schedule; it checks the most recent data
    for each configured room/device and emails a summary of any
    threshold violations.

alarm_config_TEMPLATE.yaml
    Template config file. Copy this to your own config file (any
    name you like, e.g. my_lab_config.yaml) and fill in the
    placeholders for your lab's paths, room names, thresholds, and
    email settings. This is the ONLY file most labs should need to
    edit to get the system running.

alarm_config.yaml
    The actual, filled-in config used for the APD lab's own setup.
    Included here as a REFERENCE EXAMPLE — a working, real-world
    config file showing you what a filled-out version of the
    template above actually looks like. This is not meant to be
    copied and used as-is by another lab (the paths, room names,
    and thresholds are specific to APD's rooms/hardware) — use
    alarm_config_TEMPLATE.yaml as your starting point instead, and
    refer back to this file if you want to see a concrete example
    of the format in practice.

email_credentials_TEMPLATE.txt
    Template for the file that holds the sending email's app
    password. Copy to email_credentials.txt and fill in.

recipients_TEMPLATE.txt
    Template for the list of people who receive alert emails. Copy
    to recipients.txt, one email address per line.

state/
    Directory the script uses for its own bookkeeping. Created
    automatically if it doesn't exist. Its contents are
    machine-generated, lab-specific runtime data — NOT something to
    commit to git. (If setting this up fresh, add state/*.json to
    .gitignore.) Contains:

      computed_offset_history.json
          Per-room calibration offsets (temperature, relative
          humidity, pressure) relative to your chosen reference
          room. This is NOT a config file you fill in by hand —
          see section 3 below for how to generate it.

      pressure_violations.json
          Tracks how many consecutive readings have shown a
          negative pressure difference between the reference room
          and the entrance room (if you have one configured), so
          the "prolonged" pressure alert only fires after several
          consecutive bad readings rather than one noisy sample.
          Self-healing: if this file is missing, empty, or
          corrupted, the script just starts the counter over at
          zero rather than crashing. You never need to create or
          edit this yourself.


-----------------------------------------------------------------
2. FIRST-TIME SETUP
-----------------------------------------------------------------

1. Copy alarm_config_TEMPLATE.yaml to your own config file (pick
   any name — e.g. my_lab_config.yaml — since alarm_config.yaml in
   this directory is APD's own reference example, not a blank
   starting point). Do the same for the other two templates:
       alarm_config_TEMPLATE.yaml     -> your own config file
       email_credentials_TEMPLATE.txt -> email_credentials.txt
       recipients_TEMPLATE.txt        -> recipients.txt

2. Fill in your_config.yaml. Every placeholder value (paths, room
   names, thresholds) needs a real value for your lab — comments in
   the file explain what each one means. Pay particular attention
   to:
       rooms.reference_room   — must exactly match one of the
                                 labels in rooms.prefix_labels_csv
       rooms.entrance_room    — optional; delete this line if you
                                 don't have a room like this
       particle_counter.enabled — set to true only if you actually
                                 have a particle counter

3. Fill in email_credentials.txt and recipients.txt per their own
   in-file instructions.

4. Generate your initial calibration offsets — see section 3 below.
   The script will refuse to run (on purpose) until this file
   exists with at least one valid entry.

5. Do a manual test run before putting this on a cron schedule:

       python3 alarm_email_V2.py --config your_config.yaml

   Check the printed output for errors. If your config is missing
   a required value or a path is wrong, the script will fail with
   a specific error message telling you exactly what's missing —
   fix that and re-run.

6. Once a manual run works cleanly, add it to cron (or your
   scheduler of choice) on whatever interval makes sense for how
   often new sensor data lands.


-----------------------------------------------------------------
3. CALIBRATION OFFSETS (state/computed_offset_history.json)
-----------------------------------------------------------------

Every sensor has some amount of individual measurement bias.
Rather than hardcoding correction values into the script, this
system computes them from real data and stores them in a small
JSON-lines file under state/.

WHERE THIS FILE LIVES:
    state_dir (as set in your config file) /
    computed_offset_history.json

FORMAT:
    One JSON object per line. Each line looks like:

    {"timestamp": "...", "temp_offsets": {...},
     "rh_offsets": {...}, "pressure_offsets_hpa": {...}}

    "Most recent" is simply the LAST line in the file — the script
    always reads the last line and ignores everything above it.
    Nothing needs to be deleted; the file just accumulates history
    over time as you recalibrate.

DO NOT hand-write or template-fill this file with placeholder
zeros. A "0.0" offset is indistinguishable from a real computed
"this sensor has no bias" result — if you fill in zeros just to
get the script running, you will silently disable calibration
without any warning, and every downstream threshold check will be
running against uncorrected raw sensor values. The script fails
loudly with a clear error if this file is missing or empty
specifically so that this mistake can't happen by accident — that
safeguard doesn't help you if you defeat it by hand-filling fake
values.

HOW TO GENERATE A REAL SET OF OFFSETS:
    1. Physically place every sensor/device you're monitoring in
       the SAME room as your reference room's sensor (whichever
       room you set as rooms.reference_room in the config). This
       is required — the offset calculation works by comparing
       every sensor's reading against the reference sensor's
       reading while they're all measuring the same air, so it
       only isolates true per-sensor bias when there's no real
       difference in conditions.
    2. Let them all log data for a reasonable window (at least
       several hours; a full day is better).
    3. Run:
           python3 alarm_email_V2.py --config your_config.yaml --recompute-offsets
    4. This computes fresh offsets and appends a new line to
       computed_offset_history.json. Move your sensors back to
       their normal locations afterward.

Do NOT pass --recompute-offsets on a normal/routine run — it
should only be used deliberately, during an actual co-located
calibration session. A normal run (no flag) just reads whatever
the last line in the file already says.


-----------------------------------------------------------------
4. THE PARTICLE COUNTER TOGGLE
-----------------------------------------------------------------

If your lab doesn't have a particle counter, set:

    particle_counter:
      enabled: false

in your config file. The script will skip that entire section —
it won't look for particle counter JSON files, won't expect
json_dir or prefix_labels_json to be set to anything meaningful,
and won't silently report "no violations" for a device that was
never there in the first place. If enabled is true, json_dir and
particle_counter.prefix_labels_json must both be filled in, and
the script will error out clearly if either is missing.


-----------------------------------------------------------------
5. TROUBLESHOOTING
-----------------------------------------------------------------

"Config file not found" / "Missing required config key ..."
    Something in your config file is missing or the --config path
    is wrong. The error message names the exact key and section —
    go fix that specific line.

"No offsets history file found" / "... exists but has no entries"
    state/computed_offset_history.json is missing or empty. See
    section 3 above — you need to generate this with
    --recompute-offsets before the script will run normally. Do
    not just create an empty file to make the error go away.

"<Room> data file not found!"
    The script couldn't find any CSV file matching that room's
    configured prefix in csv_dir. Check that the device is
    actually writing files, that csv_dir in the config points to
    the right place, and that the prefix in
    rooms.prefix_labels_csv exactly matches the start of the
    actual filenames being produced.

"Skipping <Room> — no data in the last hour"
    Not an error — this is the freshness check working as
    intended. That room's most recent file is more than an hour
    old, so it's excluded from this run's checks rather than being
    compared against stale data. Worth investigating if you see
    this consistently for a room that should be actively logging.

Email doesn't send / "Error sending email"
    Check email_credentials.txt has a valid app password (not your
    regular account password — use an app-specific password), and
    that email.from_address / email.smtp_host / email.smtp_port in
    the config match whatever provider you're using.


-----------------------------------------------------------------
6. A NOTE FOR LABS ADOPTING THIS SYSTEM
-----------------------------------------------------------------

The intent of this refactor was that a different lab, with
different hardware, a different number of rooms, and possibly no
particle counter at all, should be able to get this running by
editing only their own config file (plus the two credentials/
recipients templates) — never alarm_email_V2.py itself. If you
find yourself needing to edit the Python to make this work for
your setup, that's worth reporting back, since it likely means
something that should be configurable still isn't.
