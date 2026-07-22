# Enterprise AI Meeting Assistant — POC Plan

## 1. Objective

- Build a working POC (not the full production system) of an AI meeting assistant, similar to Fireflies.ai.
- Deliver a working demo by Friday.
- Use managed cloud services instead of self-hosting AI models — no GPUs, no self-run LLMs/Whisper.
- Microsoft handles the meeting side (Teams, calendar, transcript, recording).
- AWS handles the AI side (storage, transcription fallback, summarization, chat).

## 2. Architecture

```
 [Teams meeting: audio + native transcription/recording]
            |
            |  Microsoft Graph API (per-client tenant, after meeting ends)
            v
 ┌─────────────────────────────┐
 │ Microsoft 365 / Entra ID     │  - Calendar & meeting metadata
 │ (Graph API)                  │  - Transcript (.vtt, real speaker names)
 │                              │  - Recording (.mp4)
 └─────────────────────────────┘
            |
            v
 ┌─────────────────────────────┐
 │ Amazon S3                    │  stores transcript + recording
 └─────────────────────────────┘
            |
            v
 ┌─────────────────────────────┐
 │ Amazon Transcribe             │  only used for the "upload audio" fallback
 │ (multi-language: en-IN/hi-IN, │  path, when there's no Teams-native
 │  speaker diarization)         │  transcript to rely on
 └─────────────────────────────┘
            |
            v
 ┌─────────────────────────────┐
 │ Amazon Bedrock (DeepSeek V3.2)│  - Summary
 │ via Converse API              │  - Decisions
 │                                │  - Action items
 │                                │  - Chat/Q&A (scoped to this meeting only)
 └─────────────────────────────┘
            |
            v
 ┌─────────────────────────────┐
 │ Streamlit dashboard          │  Overview / Smart Search (chat) /
 │                                │  Highlights / Soundbites / Transcript
 └─────────────────────────────┘
```

- **Why no live/real-time capture:** joining a live Teams call and streaming raw audio needs Microsoft's `Calls.AccessMedia.All` permission, which requires tenant-admin consent and often a Microsoft compliance review — not realistic for a 5-day POC. Instead, the bot is invited to the meeting, Teams' own cloud recording/transcription runs natively, and we fetch the finished recording + transcript via Graph API right after the meeting ends. This is not a lesser workaround — even a future live-streaming system would still rely on this same complete post-meeting transcript as its source of truth for the final summary.
- **Why Teams' own transcript beats our own diarization:** Teams already knows real participant identity (tenant-authenticated), so its transcript comes with real speaker names attached for free. Running our own diarization (Amazon Transcribe) only produces anonymous "Speaker 0 / Speaker 1" labels, since Transcribe has no access to the tenant directory. Transcribe diarization is kept only as a fallback for the raw-audio upload path.

## 3. Tech Stack

- **Frontend:** Streamlit
- **Meeting/Identity layer:** Microsoft Graph API, Azure AD (Entra ID) App Registration
- **Cloud/AI layer:** AWS — S3 (storage), Amazon Transcribe (fallback STT), Amazon Bedrock (LLM — DeepSeek V3.2, via the provider-agnostic Converse API)
- **Hosting:** Streamlit Community Cloud (`https://teams-assist.streamlit.app/`) + a self-managed EC2 instance (`t3.micro`, Amazon Linux 2023) as a second deployment
- **Version control:** GitHub (`AI_teams_assistant`, `main` branch)

## 4. How a Meeting Gets Processed

1. Employee schedules a Teams meeting (transcription/recording enabled).
2. **Auto-detection:** a scheduler polls the organizer's calendar (`Calendars.Read` only, no special permission) and records any new online meeting it hasn't seen before, tracked in `meetings.json` with status `scheduled`.
3. Meeting happens and ends — Teams has already generated a native recording + transcript on its own.
4. **Auto-processing:** once a tracked meeting's end time has passed, the scheduler resolves its online-meeting ID (from the calendar event's join URL) and automatically fetches the transcript + recording via Graph, uploads both to S3, and generates the summary — status flips to `processed`. No one has to manually paste a meeting ID.
5. Transcript is parsed into speaker-labeled segments (real names, from Teams' own tags) as part of this.
6. Transcript text is sent to Bedrock (DeepSeek V3.2) to generate a structured summary: overview, decisions, action items, open questions.
7. Everything is displayed in the Streamlit dashboard — an audio player, an Overview card, a Smart Search/chat tab (scoped to only answer questions about this meeting), Highlights (decisions/action items), Soundbites (open questions), and a speaker-labeled Transcript panel. Processed meetings are listed under "📅 Auto-Detected Meetings" in the sidebar and can be reopened with one click.
8. A separate **"Upload recording/transcript"** mode lets someone manually upload an audio file or `.txt`/`.vtt` transcript instead — this path only needs AWS, no Microsoft/Graph setup, and works as a guaranteed fallback demo.

**What "automatic" means today vs. what's still manual:**
- Fully automatic: detecting a newly scheduled meeting, and processing it once it ends — *if* `scheduler_job.py` is run on a schedule (e.g., cron on the EC2 instance every 5-15 minutes). Streamlit itself can't run a persistent background poller; it only runs this logic when the app is open and someone clicks "Check calendar now."
- Not yet automatic: the bot does not join the live call itself. See section 8 — that piece is gated by a Microsoft approval, not by our code.

## 5. Client Onboarding (Multi-Tenant, for selling this to future clients)

- One shared Azure AD App Registration, owned by us, set to **multi-tenant**.
- A generated **one-click admin-consent link** is sent to a new client's Global Admin.
- They sign in, review the requested permissions, and click Accept — no app registration, secrets, or manual Graph API setup required on their side.
- Their tenant ID is captured automatically via redirect and stored locally (`tenants.json`); they then appear in a dropdown for selecting which client's meeting to fetch.
- Our client secret never leaves our backend; only the (non-secret) client ID appears in the consent link.

## 6. Current Status

### Done
- AWS connectivity confirmed: S3, Bedrock (DeepSeek V3.2 via Converse API), Transcribe
- Bedrock chat scoped to only answer questions about the meeting (basic prompt-injection guarding included)
- Dashboard UI rebuilt: Overview, stat line, Smart Search (chat + quick-prompt chips), Highlights, Soundbites, speaker-labeled Transcript panel, audio player
- Speaker labeling: real names parsed from Teams' VTT tags; generic Speaker 0/1 labels via Transcribe diarization for the raw-upload fallback
- Hinglish-aware transcription setting applied (Transcribe multi-language identification: en-IN/hi-IN) — not yet tested against a real sample
- Recording fetch via Graph API built (`list_recordings`, `download_recording_content`), wired into the fetch pipeline and S3 upload
- One-click multi-tenant client onboarding flow built (consent link generation, automatic tenant capture, tenant dropdown)
- Deployed to Streamlit Cloud (`https://teams-assist.streamlit.app/`)
- Deployed to a self-provisioned EC2 instance (`t3.micro`, security group open on 22/8501)
- Code pushed to GitHub (`AI_teams_assistant`, `main`), with `.env`/secrets properly excluded via `.gitignore`
- Calendar auto-detection built (`scheduler_service.detect_new_meetings`) — polls the organizer's calendar for new online meetings, tracks them in `meetings.json`
- Auto-processing built (`scheduler_service.process_due_meetings`) — once a tracked meeting ends, automatically resolves its meeting ID, fetches transcript/recording, uploads to S3, and summarizes, with no manual ID entry
- Standalone `scheduler_job.py` script for running the above on a schedule (cron), plus a manual "Check calendar now" button and tracked-meetings list in the Streamlit sidebar
- Live-join explicitly stubbed (`scheduler_service.attempt_live_join`) — not functional, clearly marked as pending Microsoft's real-time media approval (see section 8)
- **Passageway App Registration finished and confirmed working**: real Client Secret Value, redirect URI, and the four Graph permissions (`Calendars.Read`, `OnlineMeetings.Read.All`, `OnlineMeetingTranscript.Read.All`, `OnlineMeetingRecording.Read.All`) all consented — `Calendars.Read` tested live, successfully returned 10 real online meetings from a real Passageway user's calendar.
- `resolve_online_meeting_id()` fixed to work around a real Graph API quirk: the `onlineMeetings`-by-join-URL lookup requires the organizer's Object ID (GUID), not their UPN/email — parsed directly out of the join URL's `context` parameter rather than needing an extra `User.Read.All` permission.

### Pending / Blocked
- **New finding from live testing: a Teams PowerShell Application Access Policy is required for the core pipeline too**, not just the live-bot track as previously documented (see section 8's correction). Fetching a meeting by join URL fails with `"No application access policy found for this app... on the user"` without it. Needs the Passageway admin to run (in Teams PowerShell): `New-CsApplicationAccessPolicy -Identity "MeetingAssistantPolicy" -AppIds "8ec9dd7f-dc36-4f79-a522-57bb6d032ff8" -Description "..."` then `Grant-CsApplicationAccessPolicy -PolicyName "MeetingAssistantPolicy" -Identity "<organizer's Object ID>"`. This is the current, single blocker on a fully working real-data test.
- Full end-to-end test of the Teams-fetch path (list transcripts → download → summarize → chat) has never completed against a real meeting — blocked on the policy grant above.
- Streamlit Cloud secrets need the same AWS/Azure values configured (separate from local `.env`).
- Hinglish transcription setting is applied but untested against a real mixed-language sample.
- Whether Bedrock hosts a native speech-to-text model in this account was never confirmed (low priority — Transcribe already covers this need either way).

## 7. Immediate Next Steps

1. Get the Passageway admin to run the `New-CsApplicationAccessPolicy` / `Grant-CsApplicationAccessPolicy` commands above.
2. Rerun `test_graph_meeting.py` to confirm the transcript/recording/summary fetch now succeeds end-to-end.
3. Once confirmed, populate Streamlit Cloud secrets with the same Passageway credentials.
4. Confirm the EC2/Streamlit Cloud deployment the client will actually be shown on Friday.
5. If Azure setup doesn't land in time, fall back to demoing via the "Upload recording/transcript" path, which is fully working today.

## 8. Parallel Roadmap Track: Live Bot Join (not part of the Friday POC)

The client wants the eventual product to have a bot that automatically joins a live Teams call, not just process it after the fact. This is *not* achievable for Friday — not because of Microsoft approval (see correction below), but because the backend service that would do this hasn't been built yet and building/testing it is a real, multi-day engineering task on its own.

**Correction to earlier assessment:** we previously believed real-time media (`Calls.AccessMedia.All`) required a Microsoft compliance review even for single-tenant/internal use. Microsoft's own official sample (`OfficeDev/Microsoft-Teams-Samples`, `bot-calling-meeting/csharp`) shows this is granted via normal self-service admin consent, same as any other Graph permission — no separate Microsoft review needed for using this within our own tenant. Microsoft review/certification only becomes relevant if we later want to *distribute* this bot to other client tenants via the Teams Store — a separate, later concern.

**What's actually required (admin-side), confirmed against the official sample:**
- Same App Registration as the Graph-fetch integration, plus these additional Graph Application permissions: `Calls.AccessMedia.All`, `Calls.Initiate.All`, `Calls.InitiateGroupCall.All`, `Calls.JoinGroupCall.All`, `Calls.JoinGroupCallAsGuest.All`, `OnlineMeetings.ReadWrite.All` — admin consent, self-service.
- A Teams PowerShell **Application Access Policy**, granted to whichever user's meetings the bot should be able to join on behalf of (`New-CsApplicationAccessPolicy` / `Grant-CsApplicationAccessPolicy`) — admin-only, self-service, no Microsoft review.
- An **Azure Bot resource** — this needs an active Azure subscription (free trial is sufficient; F0/free tier bot itself costs nothing). Passageway currently has no subscription attached, so this is pending a free-trial signup.

**Second correction, found via real testing against Passageway (not just docs research):** the Application Access Policy above is *not* calling-bot-specific after all — resolving an online meeting by its join URL (`GET /users/{organizerId}/onlineMeetings?$filter=JoinWebUrl eq '...'`), which the *basic* post-meeting fetch pipeline also needs, fails with `"No application access policy found for this app... on the user"` without it. So this PowerShell step belongs in the **core pipeline's** requirements too (section 6), not just the live-bot track — corrected there.

**What Calls.AccessMedia.All actually gives us, and what it doesn't:** raw live audio only — no transcription. We still need a speech-to-text step for live audio (Amazon Transcribe *Streaming*, the real-time counterpart to the batch Transcribe already used for the upload path). Bedrock/DeepSeek only ever operates on text, never audio, so its role (summarize/answer questions) is unchanged — it just receives text sooner (rolling, during the meeting) instead of only after.

**Engineering status (separate folder, not touching the main POC):**
- A new sibling folder, `live-bot/` (outside `teams_assistance'`, so the working Streamlit project stays untouched), contains Microsoft's official calling/meeting bot sample (C#/.NET) as the starting point, pulled directly from `github.com/OfficeDev/Microsoft-Teams-Samples` rather than written from scratch.
- See `live-bot/README-INTEGRATION.md` for exact status, the prerequisite checklist, and where our AWS integration (Transcribe Streaming, Bedrock) needs to be plugged into the sample's existing service seams.
- **Not yet done:** .NET SDK isn't installed on this machine (only runtimes); no secrets filled in; nothing built, run, or tested; no AWS integration written yet.
- **Recommended framing for the client demo:** present the post-meeting pipeline as the working product today, and live bot-join as "next milestone, in active development" — accurate now that the Microsoft-approval blocker turned out not to apply to our own-tenant use case.
