import json
import os

_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "meetings.json")


def _load() -> list:
    if not os.path.exists(_STORE_PATH):
        return []
    with open(_STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(meetings: list) -> None:
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(meetings, f, indent=2)


def list_meetings() -> list:
    return _load()


def get_meeting(event_id: str):
    return next((m for m in _load() if m["event_id"] == event_id), None)


def upsert_meeting(meeting: dict) -> None:
    meetings = _load()
    for i, m in enumerate(meetings):
        if m["event_id"] == meeting["event_id"]:
            meetings[i] = {**m, **meeting}
            _save(meetings)
            return
    meetings.append(meeting)
    _save(meetings)
