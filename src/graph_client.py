import re

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
