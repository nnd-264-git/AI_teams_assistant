"""Picks up meeting captures the browser-bot (running on the separate Windows
EC2 box) uploaded to S3 - audio.wav + captions.json + metadata.json under
browser-bot-captures/<meeting_id>/ - and turns them into dashboard entries.

Separate from scheduler_service.py's Graph-based flow: the bot never talks
to Graph for transcripts (it captures live captions itself), so this reads
directly from S3 instead of asking Graph for a recording/transcript.
"""

import json

from . import aws_pipeline, meeting_store

CAPTURES_PREFIX = "browser-bot-captures"


def _captions_to_transcript(captions: list) -> tuple:
    segments = []
    lines = []
    for c in captions:
        speaker = c.get("speaker") or "Speaker"
        text = c.get("text", "")
        timestamp = c.get("timestamp", 0)
        minutes, seconds = divmod(int(timestamp), 60)
        start = f"00:{minutes:02d}:{seconds:02d}"
        segments.append({"speaker": speaker, "start": start, "text": text})
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines), segments


def process_browser_bot_captures() -> list:
    """Finds captures in S3 not already in meeting_store, transcribes +
    summarizes them, and saves them so they show up on the dashboard.
    Returns the list of newly-processed meeting_ids."""
    keys = aws_pipeline.list_s3_prefix(f"{CAPTURES_PREFIX}/")
    meeting_ids = sorted({key.split("/")[1] for key in keys if len(key.split("/")) > 1})

    newly_processed = []
    for meeting_id in meeting_ids:
        if meeting_store.get_meeting(meeting_id) is not None:
            continue

        try:
            metadata = json.loads(aws_pipeline.download_bytes(f"{CAPTURES_PREFIX}/{meeting_id}/metadata.json"))
            captions = json.loads(aws_pipeline.download_bytes(f"{CAPTURES_PREFIX}/{meeting_id}/captions.json"))
        except Exception:
            continue  # capture still in progress / incomplete upload

        if not captions:
            continue

        transcript, segments = _captions_to_transcript(captions)
        summary = aws_pipeline.summarize_transcript(transcript)

        meeting_store.upsert_meeting(
            {
                "event_id": meeting_id,
                "subject": metadata.get("subject", "Meeting"),
                "start": metadata.get("start", ""),
                "status": "processed",
                "transcript": transcript,
                "segments": segments,
                "summary": summary,
                "source": "browser_bot",
            }
        )
        newly_processed.append(meeting_id)

    return newly_processed
