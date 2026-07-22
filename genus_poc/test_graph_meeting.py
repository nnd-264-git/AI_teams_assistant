import requests
from src import graph_client, bot_service

user_id = "nikhil.kumawat@pssgway.com"
target_subject = "teams meeting notetaking process discussion"

events = graph_client.get_calendar_events(user_id, hours_back=24 * 30, hours_ahead=24 * 14)
event = next((e for e in events if e.get("subject") == target_subject), None)

if not event:
    print(f"Could not find an event titled '{target_subject}'")
else:
    join_url = (event.get("onlineMeeting") or {}).get("joinUrl")
    print("Event found. joinUrl present:", bool(join_url))
    if not join_url:
        print("Full event object:", event)
    else:
        try:
            meeting_id = graph_client.resolve_online_meeting_id(join_url)
            print("Resolved online meeting ID:", meeting_id)

            transcripts = graph_client.list_transcripts(user_id, meeting_id)
            print(f"Transcripts found: {len(transcripts)}")

            recordings = graph_client.list_recordings(user_id, meeting_id)
            print(f"Recordings found: {len(recordings)}")

            if transcripts:
                print("\nRunning full pipeline via bot_service.process_teams_meeting...")
                result = bot_service.process_teams_meeting(user_id, meeting_id)
                print("Transcript (first 500 chars):\n", result["transcript"][:500])
                print("\nSegments found:", len(result["segments"]))
                print("\nSummary:", result["summary"])
        except requests.HTTPError as e:
            print("FAILED:", e)
            print("Response body:", e.response.text)
        except Exception as e:
            print("FAILED:", e)
