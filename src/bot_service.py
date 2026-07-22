from . import aws_pipeline, graph_client


def process_teams_meeting(user_id: str, meeting_id: str, tenant_id: str = None) -> dict:
    transcripts = graph_client.list_transcripts(user_id, meeting_id, tenant_id)
    if not transcripts:
        raise RuntimeError("No transcript available for this meeting yet.")
    latest = transcripts[0]
    vtt = graph_client.download_transcript_content(user_id, meeting_id, latest["id"], tenant_id)
    segments = graph_client.parse_vtt_segments(vtt)
    plain_text = graph_client.vtt_to_plain_text(vtt)
    aws_pipeline.upload_bytes(vtt.encode("utf-8"), f"transcripts/{meeting_id}.vtt")

    recording_bytes = None
    recordings = graph_client.list_recordings(user_id, meeting_id, tenant_id)
    if recordings:
        recording_bytes = graph_client.download_recording_content(
            user_id, meeting_id, recordings[0]["id"], tenant_id
        )
        aws_pipeline.upload_bytes(recording_bytes, f"recordings/{meeting_id}.mp4")

    summary = aws_pipeline.summarize_transcript(plain_text)
    return {
        "transcript": plain_text,
        "segments": segments,
        "summary": summary,
        "recording_bytes": recording_bytes,
    }
