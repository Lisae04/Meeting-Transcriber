#!/usr/bin/env python3
"""
Meeting Watcher
===============

Watches for Zoom, Google Meet (in Chrome/Safari), Microsoft Teams, or FaceTime starting,
and -- ONLY after you say yes to a permission popup -- records the full meeting audio
(you + everyone else, via the "Meeting Capture" aggregate device set up in Audio MIDI
Setup -- see README.md for the one-time setup). When the meeting ends, it automatically
runs the recording through transcribe_meeting.py to produce a transcript, meeting notes,
and a summary.

It NEVER records without you explicitly clicking "Start Recording" on the popup each time.

USAGE
-----
    ./watch_meetings.command
    (or: python3 watch_meetings.py, from an activated venv)

Press Ctrl+C to stop watching. If a recording is in progress, Ctrl+C stops that too and
still runs it through the transcriber before exiting.
"""

from __future__ import annotations

import subprocess
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent.resolve()
RECORDINGS_DIR = HERE / "Recordings"
AGGREGATE_DEVICE_NAME = "Meeting Capture"
POLL_SECONDS = 8
DIALOG_TIMEOUT_SECONDS = 45

APPS = {
    "Zoom": ["zoom.us"],
    "Microsoft Teams": ["Microsoft Teams", "MSTeams"],
    "FaceTime": ["FaceTime"],
}


def is_process_running(name_substrings: list[str]) -> bool:
    try:
        output = subprocess.check_output(["ps", "-axo", "comm="], text=True, timeout=10)
    except Exception:
        return False
    lower = output.lower()
    return any(s.lower() in lower for s in name_substrings)


def is_google_meet_open() -> bool:
    """Checks open Chrome and Safari tabs for a meet.google.com URL via AppleScript.
    The first time this runs, macOS will ask you to approve automation access for
    Terminal to control Chrome/Safari -- that's expected, approve it once."""
    for app, tab_expr in [
        ("Google Chrome", 'URL of every tab of every window'),
        ("Safari", 'URL of every tab of every window'),
    ]:
        script = f'''
        if application "{app}" is not running then return ""
        tell application "{app}" to return ({tab_expr}) as string
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=10
            )
            if "meet.google.com" in result.stdout:
                return True
        except Exception:
            continue
    return False


def detect_active_meeting() -> str | None:
    """Returns a human label for whichever meeting app just started, or None."""
    for label, names in APPS.items():
        if is_process_running(names):
            return label
    if is_google_meet_open():
        return "Google Meet"
    return None


def is_meeting_still_active(label: str) -> bool:
    if label == "Google Meet":
        return is_google_meet_open()
    return is_process_running(APPS.get(label, [label]))


def ask_permission(label: str) -> bool:
    script = (
        f'display dialog "A {label} meeting appears to have started.\\n\\n'
        f'Start recording it?" '
        f'buttons {{"Not now", "Start Recording"}} default button "Start Recording" '
        f'with title "Meeting Transcriber" with icon note '
        f'giving up after {DIALOG_TIMEOUT_SECONDS}'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=DIALOG_TIMEOUT_SECONDS + 10
        )
        return "Start Recording" in result.stdout
    except Exception as exc:
        print(f"  Couldn't show the permission popup ({exc}); skipping this meeting.")
        return False


def notify(message: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "Meeting Transcriber"'],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def find_aggregate_device_index() -> str | None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    text = result.stderr  # ffmpeg prints the device list to stderr
    in_audio_section = False
    for line in text.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio_section = True
            continue
        if in_audio_section and AGGREGATE_DEVICE_NAME in line:
            # Lines look like: [AVFoundation indev @ 0x...] [1] Meeting Capture
            start = line.find("[", line.find("]") + 1)
            end = line.find("]", start)
            if start != -1 and end != -1:
                return line[start + 1:end]
    return None


def record_meeting(label: str, device_index: str) -> Path | None:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    out_path = RECORDINGS_DIR / f"{timestamp}_{label.replace(' ', '')}.wav"

    print(f"  Recording started -> {out_path.name} (say goodbye to end the meeting to stop)")
    notify(f"Recording your {label} meeting...")

    process = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "avfoundation", "-i", f":{device_index}", str(out_path)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        while is_meeting_still_active(label):
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n  Stopping recording (Ctrl+C)...")

    # Ask ffmpeg to finish the file cleanly rather than killing it outright.
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)

    if not out_path.exists() or out_path.stat().st_size == 0:
        print("  Recording produced no audio -- skipping transcription.")
        return None

    print(f"  Recording saved: {out_path}")
    return out_path


def process_recording(audio_path: Path) -> None:
    print(f"  Processing {audio_path.name} (transcript + notes + summary)...")
    result = subprocess.run(
        [sys.executable, str(HERE / "transcribe_meeting.py"), str(audio_path)],
    )
    if result.returncode == 0:
        notify("Transcript, notes, and summary are ready.")
    else:
        notify("Something went wrong processing the recording -- check Terminal.")


def main() -> int:
    print("Meeting Watcher")
    print(f"Watching for: {', '.join(list(APPS.keys()) + ['Google Meet'])}")
    print("You'll get a popup asking permission before anything is ever recorded.")
    print("Press Ctrl+C to stop watching.\n")

    device_index = find_aggregate_device_index()
    if device_index is None:
        print(
            f"WARNING: couldn't find an audio device named '{AGGREGATE_DEVICE_NAME}'.\n"
            f"Full-meeting recording needs this set up once in Audio MIDI Setup -- "
            f"see README.md's 'Full meeting audio setup' section.\n"
            f"Watching will continue, but recording will fail until that device exists.\n"
        )

    active_label = None
    try:
        while True:
            detected = detect_active_meeting()

            if detected and active_label is None:
                active_label = detected
                if ask_permission(active_label):
                    if device_index is None:
                        # Re-check in case it was set up after the script started.
                        device_index = find_aggregate_device_index()
                    if device_index is None:
                        print(f"  Can't record: '{AGGREGATE_DEVICE_NAME}' device not found.")
                        active_label = None
                    else:
                        audio_path = record_meeting(active_label, device_index)
                        active_label = None
                        if audio_path:
                            process_recording(audio_path)
                        print("\nWatching for the next meeting...\n")
                else:
                    print(f"  Okay, not recording this {active_label} meeting.")
                    # Avoid immediately re-prompting for the same still-running meeting.
                    while is_meeting_still_active(detected):
                        time.sleep(POLL_SECONDS)
                    active_label = None

            elif not detected:
                active_label = None

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped watching.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
