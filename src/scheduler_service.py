from datetime import datetime, timezone

from . import bot_service, graph_client, meeting_store


def _parse_graph_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value.split(".")[0])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def detect_new_meetings(user_id: str, tenant_id: str = None) -> list:
    """Auto-detection: polls the calendar and records any online meeting not
    already tracked. Only needs Calendars.Read - no real-time media permission."""
    events = graph_client.get_calendar_events(user_id, tenant_id)
    newly_detected = []
    for event in events:
        event_id = event["id"]
        if meeting_store.get_meeting(event_id):
            continue
        meeting = {
            "event_id": event_id,
            "subject": event.get("subject", "Untitled meeting"),
            "start": event["start"]["dateTime"],
            "end": event["end"]["dateTime"],
            "join_url": (event.get("onlineMeeting") or {}).get("joinUrl"),
            "user_id": user_id,
            "tenant_id": tenant_id,
            "status": "scheduled",
            "online_meeting_id": None,
            "transcript": None,
            "segments": None,
            "summary": None,
            "error": None,
        }
        meeting_store.upsert_meeting(meeting)
        newly_detected.append(meeting)
    return newly_detected


def attempt_live_join(meeting: dict) -> None:
    """Placeholder for automatic live joining. NOT functional yet: Teams calling
    bots require Microsoft's real-time media approval (Calls.AccessMedia.All) -
    a Microsoft-reviewed process, not something admin consent alone grants (see
    plan.md section 8). Once that access is approved, the Bot Framework calling
    logic goes here; until then, meetings fall back to post-meeting processing."""
    raise NotImplementedError(
        "Live join is pending Microsoft's real-time media approval - "
        "falling back to post-meeting processing for this meeting."
    )


def process_due_meetings(tenant_id: str = None) -> list:
    """For every tracked meeting whose end time has passed and isn't processed
    yet, resolve its online meeting ID, fetch the finished transcript/recording,
    and summarize it. This is what makes the pipeline run without anyone
    manually clicking 'Fetch & process' for each meeting."""
    processed = []
    now = datetime.now(timezone.utc)
    for meeting in meeting_store.list_meetings():
        if meeting["status"] != "scheduled":
            continue
        if _parse_graph_datetime(meeting["end"]) > now:
            continue
        try:
            if not meeting.get("online_meeting_id") and meeting.get("join_url"):
                meeting["online_meeting_id"] = graph_client.resolve_online_meeting_id(
                    meeting["join_url"], meeting["tenant_id"]
                )
            result = bot_service.process_teams_meeting(
                meeting["user_id"], meeting["online_meeting_id"], meeting["tenant_id"]
            )
            meeting.update(
                status="processed",
                transcript=result["transcript"],
                segments=result["segments"],
                summary=result["summary"],
            )
            meeting_store.upsert_meeting(meeting)
            processed.append(meeting)
        except Exception as e:
            meeting["status"] = "failed"
            meeting["error"] = str(e)
            meeting_store.upsert_meeting(meeting)
    return processed
