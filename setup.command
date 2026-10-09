#!/bin/zsh
# One-time setup: creates a virtual environment and installs everything needed.
# Double-click this file in Finder to run it (or: chmod +x setup.command && ./setup.command)

cd "$(dirname "$0")" || exit 1

echo "== Meeting Transcriber setup =="

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found. Install it from https://www.python.org/downloads/ (or 'brew install python') and re-run this."
    read -r "?Press Enter to close..."
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg not found -- it's required to read mp3/m4a files."
    if command -v brew >/dev/null 2>&1; then
        echo "Installing it with Homebrew..."
        brew install ffmpeg
    else
        echo "Install Homebrew (https://brew.sh) then run: brew install ffmpeg"
        echo "Continuing setup anyway, but transcription will fail until ffmpeg is installed."
    fi
fi

echo "Creating virtual environment (venv/)..."
python3 -m venv venv
source venv/bin/activate

echo "Installing Python packages (this can take a few minutes the first time)..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "Created .env -- open it in any text editor and paste in your Anthropic (or OpenAI) API key."
fi

echo ""
echo "-- Optional: live meeting recording --"
if command -v brew >/dev/null 2>&1; then
    if ! system_profiler SPAudioDataType 2>/dev/null | grep -qi "BlackHole"; then
        echo "Installing BlackHole (free virtual audio device, needed to record full meetings)..."
        brew install blackhole-2ch
    else
        echo "BlackHole is already installed."
    fi
else
    echo "Homebrew not found -- skipping BlackHole install. Only needed if you want"
    echo "watch_meetings.command to record full meetings automatically; see README.md."
fi
echo "One more manual step is needed before live recording works: creating a 'Meeting"
echo "Capture' device in Audio MIDI Setup. See the 'Full meeting audio setup' section"
echo "in README.md -- it only takes a few minutes and only needs doing once."

echo ""
echo "Setup complete!"
echo "To transcribe a recording: drag an mp3/m4a/wav file onto run.command"
echo "To auto-record live meetings: double-click watch_meetings.command"
echo "(See README.md for details on both.)"
read -r "?Press Enter to close..."
