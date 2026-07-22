import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import msal
import requests

from . import config

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_CUE_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->\s*(\d{2}:\d{2}:\d{2})\.\d{3}")
_VOICE_TAG_RE = re.compile(r"^<v\s+([^>]+)>(.*?)(</v>)?$", re.DOTALL)


def build_admin_consent_url(redirect_uri: str, state: str = "") -> str:
    """One-click consent link for onboarding a new client tenant. Their Global Admin
    visits this, reviews the permissions already configured on our app registration,
    and clicks Accept - no app registration, secrets, or manual Graph API setup
    needed on their side. Requires the app registration to be multi-tenant."""
    if not config.AZURE_CLIENT_ID:
        raise RuntimeError("AZURE_CLIENT_ID is not configured - set it in .env (or Streamlit secrets).")
    params = {"client_id": config.AZURE_CLIENT_ID, "redirect_uri": redirect_uri}
    if state:
        params["state"] = state
    query = "&".join(f"{k}={requests.utils.quote(v, safe='')}" for k, v in params.items())
    return f"https://login.microsoftonline.com/organizations/adminconsent?{query}"


def _get_token(tenant_id: str = None) -> str:
    tenant_id = tenant_id or config.AZURE_TENANT_ID
    if not (tenant_id and config.AZURE_CLIENT_ID and config.AZURE_CLIENT_SECRET):
        raise RuntimeError(
            "Azure app registration credentials are missing. Set AZURE_CLIENT_ID and "
            "AZURE_CLIENT_SECRET in .env, and provide a tenant (via client onboarding, "
            "or AZURE_TENANT_ID as the default), to fetch meetings from Teams."
        )
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        config.AZURE_CLIENT_ID, authority=authority, client_credential=config.AZURE_CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=config.GRAPH_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Graph auth failed: {result.get('error_description')}")
    return result["access_token"]


def get_calendar_events(
    user_id: str, tenant_id: str = None, hours_back: int = 24, hours_ahead: int = 24 * 14
) -> list:
    """The calendar auto-detection piece - only needs Calendars.Read, no
    real-time media permission. Returns online-meeting events in the window."""
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'}
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
    end = (now + timedelta(hours=hours_ahead)).strftime("%Y-%m-%dT%H:%M:%S")
    url = f"{GRAPH_BASE}/users/{user_id}/calendarView"
    resp = requests.get(
        url, headers=headers, params={"startDateTime": start, "endDateTime": end}, timeout=30
    )
    resp.raise_for_status()
    events = resp.json().get("value", [])
    return [e for e in events if e.get("isOnlineMeeting")]


def _extract_organizer_oid(join_url: str) -> str:
    """The onlineMeetings-by-joinUrl lookup requires the organizer's Object ID
    (GUID), not their UPN/email - a quirk specific to this one endpoint. The
    join URL already carries that GUID in its 'context' query parameter, so we
    parse it out rather than needing an extra User.Read.All permission/call."""
    context_raw = parse_qs(urlparse(join_url).query).get("context", [None])[0]
    if not context_raw:
        raise RuntimeError("Could not find organizer ID in the meeting join URL.")
    oid = json.loads(context_raw).get("Oid")
    if not oid:
        raise RuntimeError("Could not find organizer ID (Oid) in the meeting join URL context.")
    return oid


def resolve_online_meeting_id(join_url: str, tenant_id: str = None) -> str:
    organizer_oid = _extract_organizer_oid(join_url)
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/users/{organizer_oid}/onlineMeetings"
    resp = requests.get(url, headers=headers, params={"$filter": f"JoinWebUrl eq '{join_url}'"}, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("value", [])
    if not results:
        raise RuntimeError("Could not resolve online meeting ID from join URL - meeting may not have started yet.")
    return results[0]["id"]


def list_transcripts(user_id: str, meeting_id: str, tenant_id: str = None) -> list:
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/users/{user_id}/onlineMeetings/{meeting_id}/transcripts"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def download_transcript_content(user_id: str, meeting_id: str, transcript_id: str, tenant_id: str = None) -> str:
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/vtt"}
    url = (
        f"{GRAPH_BASE}/users/{user_id}/onlineMeetings/{meeting_id}"
        f"/transcripts/{transcript_id}/content"
    )
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def list_recordings(user_id: str, meeting_id: str, tenant_id: str = None) -> list:
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/users/{user_id}/onlineMeetings/{meeting_id}/recordings"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def download_recording_content(user_id: str, meeting_id: str, recording_id: str, tenant_id: str = None) -> bytes:
    token = _get_token(tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    url = (
        f"{GRAPH_BASE}/users/{user_id}/onlineMeetings/{meeting_id}"
        f"/recordings/{recording_id}/content"
    )
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.content


def parse_vtt_segments(vtt_content: str) -> list:
    """Parses Teams' WEBVTT transcript into speaker-labeled segments, preserving
    the real speaker names Teams already attaches (via <v Speaker Name> tags)
    instead of discarding them."""
    segments = []
    for block in re.split(r"\n\s*\n", vtt_content.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_idx = next((i for i, line in enumerate(lines) if _CUE_TIME_RE.search(line)), None)
        if time_idx is None:
            continue
        start = _CUE_TIME_RE.search(lines[time_idx]).group(1)
        raw_text = " ".join(lines[time_idx + 1:]).strip()
        if not raw_text:
            continue
        voice_match = _VOICE_TAG_RE.match(raw_text)
        if voice_match:
            speaker = voice_match.group(1).strip()
            text = voice_match.group(2).strip()
        else:
            speaker = None
            text = re.sub(r"</?v[^>]*>", "", raw_text).strip()
        segments.append({"speaker": speaker, "start": start, "text": text})
    return segments


def vtt_to_plain_text(vtt_content: str) -> str:
    segments = parse_vtt_segments(vtt_content)
    return "\n".join(f"{seg['speaker']}: {seg['text']}" if seg["speaker"] else seg["text"] for seg in segments)
