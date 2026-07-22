import requests
from src import graph_client

user_id = "nikhil.kumawat@pssgway.com"

try:
    events = graph_client.get_calendar_events(user_id, hours_back=24 * 30, hours_ahead=24 * 14)
    print(f"SUCCESS. Found {len(events)} online meeting(s) in the window.")
    for e in events:
        print("-", e.get("subject"), "|", e["start"]["dateTime"], "->", e["end"]["dateTime"])
except requests.HTTPError as e:
    print("FAILED:", e)
    print("Response body:", e.response.text)
except Exception as e:
    print("FAILED:", e)
