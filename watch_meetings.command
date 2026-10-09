#!/bin/zsh
# Double-click to start watching for meetings (Zoom, Google Meet, Teams, FaceTime).
# You'll get a popup asking permission before it ever records anything.
# Leave this Terminal window open while you want it watching; press Ctrl+C (or close
# the window) to stop.

cd "$(dirname "$0")" || exit 1

if [ ! -d "venv" ]; then
    echo "Setup hasn't been run yet. Double-click setup.command first."
    read -r "?Press Enter to close..."
    exit 1
fi

source venv/bin/activate
python3 watch_meetings.py

read -r "?Press Enter to close..."
