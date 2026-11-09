# Meeting Transcriber

**Turn a meeting recording into a transcript, detailed notes and a one-page summary of decisions and action items, with the audio never leaving your laptop.**

## Why I built this

I was spending hours after client calls rewriting my notes into decisions and to-dos, and missing things in the process.
I wanted a tool that would:

- keep the audio private (transcription runs locally with faster-whisper)
- pull out **decisions, action items (owner / task / due date) and open questions**, not just a wall of text
- refuse to make things up: if a name or date wasn't said clearly, the summary says "not specified"
- show what each run costs (token usage and estimated $ are printed every time)

## How it works

```
recording (.mp3/.m4a/.wav) ──► faster-whisper (local) ──► timestamped transcript
                                                     └──► LLM (Claude or OpenAI) ──► meeting notes + summary
```

Optional: `watch_meetings.py` detects a Zoom, Teams, FaceTime or Google Meet call, **asks before recording**, and runs the pipeline when the call ends.

## What I'd add next

- Speaker labels (who said what)
- Push action items straight into Jira or Notion
- A small evaluation set: compare the summary against hand-written notes for a few test meetings

## One-time setup

1. Double-click **`setup.command`**.
   - If a security warning pops up ("cannot be opened because it is from an
     unidentified developer"), right-click the file → **Open** → **Open**,
     then it will run normally from then on.
   - This creates a private Python environment in this folder and installs
     everything needed (takes a few minutes). It also installs `ffmpeg` via
     Homebrew if you don't already have it, and (if you have Homebrew)
     installs BlackHole, a free virtual audio device used for live meeting
     recording.
2. Open the new **`.env`** file in this folder (created automatically) in
   any text editor, and paste in your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   Get a key at https://console.anthropic.com/ (Settings → API Keys). If
   you'd rather use OpenAI, put your key in `OPENAI_API_KEY=` instead and
   pass `--provider openai` when running (see below).
3. **Only if you want live meeting recording** (skip this if you'll just drag
   in recordings you already have): follow "Full meeting audio setup" below.
   It's a one-time, ~5 minute manual step in a macOS app called Audio MIDI
   Setup — there's no way to automate it from a script, but it's simple.

You only need to do all of this once.

## Processing a recording you already have

**Easiest way:** drag one or more audio files onto the **`run.command`** icon
in Finder. A Terminal window opens, shows progress, and closes when done (or
press Enter to close it sooner).

**From Terminal**, in this folder:
```bash
./run.command meeting.mp3
./run.command standup.mp3 planning.m4a        # multiple files at once
```

**Advanced options** (run the underlying script directly for these):
```bash
source venv/bin/activate
python3 transcribe_meeting.py meeting.mp3 --model medium      # more accurate, slower
python3 transcribe_meeting.py meeting.mp3 --provider openai   # use OpenAI instead of Claude
python3 transcribe_meeting.py meeting.mp3 --out-dir ~/Documents/Meeting\ Notes
```

Run `python3 transcribe_meeting.py --help` for the full list.

## Live meeting recording

Double-click **`watch_meetings.command`**. It watches in the background for
Zoom, Microsoft Teams, FaceTime, or a Google Meet tab in Chrome/Safari.

**It will never record without asking you first.** The moment it notices one
of those has started, you'll get a macOS popup:

> A Zoom meeting appears to have started. Start recording it?
> [Not now]  [Start Recording]

- Click **Start Recording** and it records the full meeting (you and everyone
  else) to this folder's `Recordings/` subfolder.
- Click **Not now** (or ignore it for 45 seconds) and nothing is recorded.

When the meeting app closes (or the Google Meet tab is gone), recording stops
automatically and the file is immediately run through the same
transcript + notes + summary pipeline as above — you'll get a macOS
notification when it's ready. You can also press **Ctrl+C** in the Terminal
window at any time to stop watching (this also cleanly stops a recording in
progress and still processes it).

The first time it runs, macOS will separately ask you to approve a couple of
its own permissions — these are normal, one-time, and you're in control of
each:
- **Microphone access**, for recording.
- **Automation access** for Terminal to check Chrome/Safari tabs (only used
  to notice a `meet.google.com` tab — it doesn't read anything else about
  your browsing).
- **Notifications**, so it can tell you when a transcript is ready.

### Full meeting audio setup (one-time, needed only for live recording)

To capture *everyone* in the meeting (not just your microphone), macOS needs
a way to route both your mic and the meeting's speaker audio into one
recording input. This uses BlackHole (installed by `setup.command`) and
macOS's built-in **Audio MIDI Setup** app:

1. Open **Audio MIDI Setup** (Spotlight search, or Applications → Utilities).
2. Click the **+** button in the bottom-left corner → **Create Multi-Output Device**.
   - Check both your normal output (e.g. "MacBook Air Speakers") and
     "BlackHole 2ch."
   - This is what you'll pick as your Mac's speaker (or the meeting app's audio output) while
     recording, so you can still hear the meeting *and* it also gets captured.
3. Click **+** again → **Create Aggregate Device**.
   - Check your normal microphone (e.g. "MacBook Air Microphone") and
     "BlackHole 2ch."
   - Rename this new device to exactly **`Meeting Capture`** (double-click its
     name in the list) — the app looks for this exact name.
4. Before joining a meeting: in the meeting app's (or macOS's) audio output
   settings, switch your speaker output to the **Multi-Output Device** you
   made in step 2, so both you and the recording can hear/capture it.
5. That's it — `watch_meetings.command` will find the "Meeting Capture"
   device automatically from here on. You only need to redo step 4 (switching
   output) each time you want the mix to include what others say; steps 1-3
   are one-time.

If you'd rather skip this setup, `watch_meetings.command` still works to
detect meetings and ask permission, but recording will fail with a clear
message telling you the device isn't set up yet — it won't record mic-only
by accident.

### A note on consent

In Canada, it's generally legal to record a call as long as one participant
(you) consents — but many workplaces and clients still expect you to tell
other attendees a meeting is being recorded, especially for client work.
Check your organization's policy before recording client calls.

## Notes on quality / speed

- Default Whisper model is `small` — a good balance of speed and accuracy for
  clear meeting audio. For noisy recordings or multiple accents, try
  `--model medium` (slower, more accurate). `tiny`/`base` are fastest but
  less reliable.
- A 1-hour meeting typically takes a few minutes to transcribe on an M-series
  MacBook Air with the `small` model.
- The notes/summary step is instructed to only use what's actually in the
  transcript (no invented names, dates, or decisions) — if something wasn't
  said clearly, it will say "not specified" rather than guess.
- If you don't add an API key, the transcript is still produced and saved —
  you'll just see a note that the notes/summary step was skipped.
- Every run prints the exact token usage and an estimated cost for the
  notes/summary API call, e.g. `Tokens used: 3,214 in / 612 out (~$0.0128)`.

## Files in this folder

| File | Purpose |
|---|---|
| `transcribe_meeting.py` | Transcribes + writes notes/summary for one recording |
| `watch_meetings.py` | Watches for live meetings, records (with permission), then calls the above |
| `requirements.txt` | Python packages needed |
| `setup.command` | Run once to install everything |
| `run.command` | Drag existing recordings onto this to process them |
| `watch_meetings.command` | Double-click to start watching for live meetings |
| `.env` | Your API key (created by setup, not shared anywhere) |
| `venv/` | Private Python environment (created by setup) |
| `Recordings/` | Where live-recorded meetings are saved (created on first use) |

## Troubleshooting

- **"ffmpeg not found"**: install Homebrew (https://brew.sh), then run
  `brew install ffmpeg`, then re-run `setup.command`.
- **"No API key found for provider..."**: open `.env` and make sure the key
  line has no quotes or extra spaces, e.g. `ANTHROPIC_API_KEY=sk-ant-abc123`.
- **Very long meetings are slow**: try a smaller model (`--model base`) or
  let it run in the background — it doesn't need your attention once started.
- **"cannot be opened because it is from an unidentified developer"**:
  right-click the `.command` file → Open → Open (only needed the first time).
- **`watch_meetings.command` says the "Meeting Capture" device isn't found**:
  you haven't done the one-time Audio MIDI Setup steps above yet, or the
  device got renamed — reopen Audio MIDI Setup and check the exact name.
- **The permission popup didn't appear**: check you haven't accidentally
  clicked away Terminal's automation/notification permission prompts as
  "Don't Allow" — go to System Settings → Privacy & Security → Automation
  (and → Notifications) and make sure Terminal is allowed.
