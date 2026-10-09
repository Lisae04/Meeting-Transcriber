#!/usr/bin/env python3
"""
Meeting Transcriber & Summarizer
=================================

Turns an mp3 (or other audio) recording of a meeting into:
  1. A full text transcript   ({name}_transcript.txt)
  2. Detailed meeting notes   ({name}_meeting_notes.md)
  3. A concise summary        ({name}_summary.md)

Transcription runs locally (faster-whisper, no internet or API key needed).
Summarization calls an LLM API (Anthropic Claude by default, OpenAI as an
alternative) so you need an API key for that step -- see README.md.

USAGE
-----
    python3 transcribe_meeting.py meeting1.mp3 [meeting2.mp3 ...]
    python3 transcribe_meeting.py meeting.mp3 --model medium
    python3 transcribe_meeting.py meeting.mp3 --provider openai
    python3 transcribe_meeting.py meeting.mp3 --out-dir ~/Documents/Meeting\\ Notes

Run with -h / --help for all options.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

# Load a local .env file (if present) so API keys don't need to be exported
# by hand every session.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".wma"}

# Markers the model is told to emit so we can split one response into two files
# (one API call instead of two -- cheaper and faster than calling twice).
NOTES_MARKER = "===MEETING NOTES==="
SUMMARY_MARKER = "===EXECUTIVE SUMMARY==="

NOTES_AND_SUMMARY_SYSTEM_PROMPT = f"""You are an assistant that turns raw meeting transcripts \
into two documents: detailed meeting notes, and a concise executive summary. Use ONLY \
information that is actually present in the transcript -- never invent names, dates, numbers, \
or decisions that were not said. If something is unclear or not mentioned (e.g. no due date \
was given), say "not specified" rather than guessing.

Produce BOTH documents below, in exactly this order, each beginning with its marker line on
its own (the marker lines must appear verbatim, with nothing else on that line):

{NOTES_MARKER}
Detailed, chronological meeting notes in Markdown. Break the meeting into the topics/agenda
items it actually covered, using "## <topic>" headings in the order they came up. Under each
heading, write 3-8 bullet points capturing what was actually discussed: who said what (when
speakers are distinguishable), specific numbers/names/dates mentioned, concerns raised, and
how the discussion resolved. This should read like thorough minutes someone could use to
reconstruct the meeting -- more detail than the summary below, but still your own clear
wording, not a verbatim transcript dump.

{SUMMARY_MARKER}
A concise executive summary in Markdown, with exactly these sections in this order:

## Overview
A 2-4 sentence summary of what the meeting was about and its outcome.

## Key Discussion Points
Bullet list of the main topics discussed, one bullet per topic, each 1-2 sentences.

## Decisions Made
Bullet list of concrete decisions reached. Write "No firm decisions were recorded." if none.

## Action Items
A markdown table with columns: Owner | Task | Due Date. Use "not specified" for any
missing field. Write "No action items were recorded." if none.

## Open Questions / Follow-ups
Bullet list of unresolved questions or things flagged for later. Write "None recorded."
if none.

Keep both documents factual -- this will be pasted directly into a report or shared with
people who did not attend."""


def parse_notes_and_summary(text: str) -> tuple[str, str]:
    """Splits the model's combined response into (notes, summary) using the markers above.

    Falls back gracefully if the model didn't include both markers exactly, so a formatting
    slip never loses content -- everything returned is still written to disk somewhere.
    """
    if NOTES_MARKER in text and SUMMARY_MARKER in text:
        notes_part, summary_part = text.split(SUMMARY_MARKER, 1)
        notes = notes_part.split(NOTES_MARKER, 1)[1].strip()
        summary = summary_part.strip()
        return notes, summary

    # Markers missing/malformed: don't lose the content, just put it all in the summary
    # file and leave notes empty so it's obvious something needs a look.
    return "", text.strip()

# Known $ per million tokens, for printing a rough cost estimate after each summary.
# Not exhaustive -- if a model isn't listed, token counts are still shown, just no $ figure.
# (Verified against provider pricing pages as of Sept 2026; check your provider's console
# for exact/current billing.)
TOKEN_PRICING_PER_MTOK = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "gpt-4o": (2.50, 10.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> str | None:
    pricing = TOKEN_PRICING_PER_MTOK.get(model)
    if not pricing:
        return None
    in_price, out_price = pricing
    cost = (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return f"${cost:.4f}"


def human_time(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


def validate_input_file(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{path.suffix}' for {path.name}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if path.stat().st_size == 0:
        raise ValueError(f"File is empty: {path}")
    return path


def transcribe_audio(audio_path: Path, model_size: str) -> tuple[str, str]:
    """Returns (plain_transcript, timestamped_transcript)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError(
            "faster-whisper is not installed. Run setup.command first, "
            "or: pip install faster-whisper"
        ) from exc

    print(f"  Loading Whisper model '{model_size}' (first run downloads it, ~1-2 min)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"  Transcribing {audio_path.name} (this can take a while for long recordings)...")
    start = time.time()
    segments, info = model.transcribe(str(audio_path), beam_size=5, vad_filter=True)

    plain_lines = []
    timestamped_lines = []
    last_report = time.time()
    for segment in segments:
        plain_lines.append(segment.text.strip())
        timestamped_lines.append(
            f"[{human_time(segment.start)} - {human_time(segment.end)}] {segment.text.strip()}"
        )
        if time.time() - last_report > 15:
            print(f"    ...transcribed up to {human_time(segment.end)}")
            last_report = time.time()

    elapsed = time.time() - start
    print(f"  Done in {human_time(elapsed)}. Detected language: {info.language} "
          f"(confidence {info.language_probability:.0%})")

    if not plain_lines:
        raise RuntimeError(
            "No speech was detected in this file. Check the audio isn't silent/corrupted."
        )

    return " ".join(plain_lines), "\n".join(timestamped_lines)


def summarize_with_anthropic(transcript: str, api_key: str, model: str) -> tuple[str, int, int]:
    """Returns (summary_text, input_tokens, output_tokens)."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=6000,
        system=NOTES_AND_SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Meeting transcript:\n\n{transcript}"}],
    )
    # Some models return extra blocks (e.g. thinking blocks) before the actual text --
    # find every text block rather than assuming content[0] is it.
    text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"Anthropic response had no text content (got block types: "
            f"{[getattr(b, 'type', type(b).__name__) for b in response.content]})"
        )
    summary_text = "\n".join(text_blocks).strip()
    return summary_text, response.usage.input_tokens, response.usage.output_tokens


def summarize_with_openai(transcript: str, api_key: str, model: str) -> tuple[str, int, int]:
    """Returns (summary_text, input_tokens, output_tokens)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": NOTES_AND_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Meeting transcript:\n\n{transcript}"},
        ],
    )
    usage = response.usage
    return (
        response.choices[0].message.content,
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


def summarize_transcript(transcript: str, provider: str) -> str | None:
    """Returns the combined notes+summary markdown (still containing both markers, split
    later by parse_notes_and_summary), or None if no API key is configured.

    Also prints the exact input/output token counts reported by the API (plus a rough
    $ estimate for known models), so you don't have to guess."""
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        if not api_key:
            return None
        print(f"  Summarizing with Anthropic ({model})...")
        summary, in_tok, out_tok = summarize_with_anthropic(transcript, api_key, model)

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        if not api_key:
            return None
        print(f"  Summarizing with OpenAI ({model})...")
        summary, in_tok, out_tok = summarize_with_openai(transcript, api_key, model)

    else:
        raise ValueError(f"Unknown provider: {provider}")

    cost = estimate_cost(model, in_tok, out_tok)
    cost_str = f" (~{cost})" if cost else " (check your provider dashboard for exact cost)"
    print(f"  Tokens used: {in_tok:,} in / {out_tok:,} out{cost_str}")
    return summary


def process_file(audio_path: Path, model_size: str, provider: str, out_dir: Path | None) -> None:
    print(f"\n=== {audio_path.name} ===")
    target_dir = out_dir if out_dir else audio_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem

    plain_transcript, timestamped_transcript = transcribe_audio(audio_path, model_size)

    transcript_path = target_dir / f"{stem}_transcript.txt"
    transcript_path.write_text(timestamped_transcript, encoding="utf-8")
    print(f"  Transcript saved: {transcript_path}")

    combined = summarize_transcript(plain_transcript, provider)
    if combined is None:
        print(
            f"  No API key found for provider '{provider}' -- skipping notes/summary. "
            f"Add a key to .env and re-run, or use --provider to switch providers. "
            f"(Transcript was still saved above.)"
        )
        return

    notes, summary = parse_notes_and_summary(combined)

    if notes:
        notes_path = target_dir / f"{stem}_meeting_notes.md"
        notes_path.write_text(f"# Meeting Notes: {stem}\n\n" + notes, encoding="utf-8")
        print(f"  Meeting notes saved: {notes_path}")
    else:
        print("  Note: model response didn't include the expected notes marker -- "
              "full response was saved to the summary file instead so nothing is lost.")

    summary_path = target_dir / f"{stem}_summary.md"
    summary_path.write_text(f"# Meeting Summary: {stem}\n\n" + summary, encoding="utf-8")
    print(f"  Summary saved:       {summary_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe and summarize meeting audio files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("audio_files", nargs="+", help="Path(s) to mp3/wav/m4a/etc. files")
    parser.add_argument(
        "--model",
        default=os.environ.get("WHISPER_MODEL", "small"),
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size: bigger = more accurate but slower (default: small)",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("SUMMARY_PROVIDER", "anthropic"),
        choices=["anthropic", "openai"],
        help="LLM provider for summarization (default: anthropic)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Where to save transcript/summary files (default: next to each input file)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None

    exit_code = 0
    for raw_path in args.audio_files:
        try:
            audio_path = validate_input_file(raw_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Skipping '{raw_path}': {exc}", file=sys.stderr)
            exit_code = 1
            continue

        try:
            process_file(audio_path, args.model, args.provider, out_dir)
        except Exception as exc:  # noqa: BLE001 - surface any failure per-file, keep going
            print(f"Failed to process '{audio_path.name}': {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
