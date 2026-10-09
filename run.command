#!/bin/zsh
# Drag one or more audio files onto this icon in Finder to transcribe + summarize them.
# (Or run from Terminal: ./run.command meeting.mp3 [meeting2.mp3 ...])

cd "$(dirname "$0")" || exit 1

if [ ! -d "venv" ]; then
    echo "Setup hasn't been run yet. Double-click setup.command first."
    read -r "?Press Enter to close..."
    exit 1
fi

source venv/bin/activate

if [ "$#" -eq 0 ]; then
    echo "No file given. Drag an mp3/m4a/wav file onto this icon, or run:"
    echo "  ./run.command meeting.mp3"
    read -r "?Press Enter to close..."
    exit 1
fi

python3 transcribe_meeting.py "$@"

echo ""
read -r "?Press Enter to close..."
