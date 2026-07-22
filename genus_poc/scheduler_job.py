"""Run this on a schedule (e.g. cron every 5-15 minutes) to make calendar
detection and post-meeting processing actually automatic - Streamlit only runs
this logic when someone has the app open and clicks a button, so true
"no one has to trigger anything" automation needs this running independently.

Usage: python scheduler_job.py <organizer_user_id>
"""
import sys

from src import scheduler_service, tenant_store


def main():
    if len(sys.argv) < 2:
        print("Usage: python scheduler_job.py <organizer_user_id>")
        return

    user_id = sys.argv[1]
    tenant_ids = [t["tenant_id"] for t in tenant_store.list_tenants()] or [None]

    for tenant_id in tenant_ids:
        for meeting in scheduler_service.detect_new_meetings(user_id, tenant_id):
            print(f"Detected: {meeting['subject']} ({meeting['start']})")
        for meeting in scheduler_service.process_due_meetings(tenant_id):
            print(f"Processed: {meeting['subject']}")


if __name__ == "__main__":
    main()
