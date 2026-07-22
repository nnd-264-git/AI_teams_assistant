import streamlit as st

from src import aws_pipeline, bot_service, browser_bot_ingest, config, graph_client, meeting_store, scheduler_service, tenant_store

st.set_page_config(
    page_title="Enterprise AI Meeting Assistant",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Design tokens (light theme, validated categorical/status palette) --------
HEADER_FROM = "#eaf2fc"
HEADER_TO = "#cde2fb"
ACCENT_BLUE = "#2a78d6"
ACCENT_BLUE_DARK = "#184f95"
GOOD = "#0ca30c"
WARNING = "#e0940c"
SURFACE = "#ffffff"
PAGE_PLANE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
BORDER = "rgba(11,11,11,0.10)"
CATEGORICAL_HUES = ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#1baf7a", "#eb6834", "#4a3aa7", "#e34948"]

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {PAGE_PLANE}; }}
    #MainMenu, footer {{ visibility: hidden; }}

    .mx-header {{
        background: linear-gradient(135deg, {HEADER_FROM} 0%, {HEADER_TO} 100%);
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 24px 32px;
        margin-bottom: 16px;
        color: {INK_PRIMARY};
    }}
    .mx-header .tag {{
        display: inline-block;
        color: {ACCENT_BLUE_DARK};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 8px;
    }}
    .mx-header h1 {{ font-size: 26px; margin: 0 0 4px 0; color: {INK_PRIMARY}; }}
    .mx-header p {{ margin: 0; color: {INK_SECONDARY}; font-size: 14px; }}

    .mx-stats {{ color: {INK_MUTED}; font-size: 13px; margin: -6px 0 16px 4px; }}

    .mx-panel {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 16px 18px;
        height: 100%;
    }}
    .mx-panel h4 {{ margin: 0 0 12px 0; font-size: 14px; color: {INK_PRIMARY}; }}

    .mx-chip {{
        display: inline-block;
        background: #eef4fc;
        color: {ACCENT_BLUE_DARK};
        font-size: 12px;
        font-weight: 600;
        padding: 5px 12px;
        border-radius: 999px;
        margin: 0 6px 6px 0;
        border: 1px solid {BORDER};
    }}

    .mx-comment {{ display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid {BORDER}; }}
    .mx-comment:last-child {{ border-bottom: none; }}
    .mx-avatar {{
        min-width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        color: white; font-size: 12px; font-weight: 700; flex-shrink: 0;
    }}
    .mx-comment-body .name {{ font-size: 13px; font-weight: 700; color: {INK_PRIMARY}; }}
    .mx-comment-body .time {{ font-size: 11px; color: {INK_MUTED}; margin-left: 6px; font-weight: 400; }}
    .mx-comment-body .text {{ font-size: 14px; color: {INK_SECONDARY}; margin-top: 2px; line-height: 1.5; }}
    .mx-empty {{ color: {INK_MUTED}; font-size: 13px; font-style: italic; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def speaker_color(speaker: str) -> str:
    colors = st.session_state.setdefault("speaker_colors", {})
    if speaker not in colors:
        colors[speaker] = CATEGORICAL_HUES[len(colors) % len(CATEGORICAL_HUES)]
    return colors[speaker]


def initials(name: str) -> str:
    parts = [p for p in (name or "?").split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else parts[0][:2].upper()


def comment_row(name: str, sub: str, text: str) -> str:
    color = speaker_color(name)
    return f"""
    <div class="mx-comment">
        <div class="mx-avatar" style="background:{color}">{initials(name)}</div>
        <div class="mx-comment-body">
            <span class="name">{name}</span><span class="time">{sub}</span>
            <div class="text">{text}</div>
        </div>
    </div>
    """


st.markdown(
    """
    <div class="mx-header">
        <div class="tag">Private &bull; Secure &bull; AI-Powered</div>
        <h1>Enterprise AI Meeting Assistant</h1>
        <p>Transcripts, summaries, decisions, and action items — pulled straight from Teams, kept inside company infrastructure.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "transcript" not in st.session_state:
    st.session_state.transcript = None
    st.session_state.segments = []
    st.session_state.summary = None
    st.session_state.chat_history = []
    st.session_state.recording_bytes = None

query_params = st.query_params
if query_params.get("admin_consent") == "True" and "tenant" in query_params:
    tenant_store.add_tenant(query_params["tenant"])
    st.query_params.clear()
    st.success(f"Client tenant {query_params.get('tenant')} onboarded successfully.")
elif "error" in query_params:
    st.error(f"Consent failed: {query_params.get('error_description', query_params['error'])}")
    st.query_params.clear()

with st.sidebar:
    with st.expander("🔗 Client Onboarding"):
        st.caption("Send a client's admin this link. One click, no app registration or secrets on their side.")
        redirect_uri = st.text_input("Redirect URI", value="http://localhost:8501")
        if st.button("Generate consent link", use_container_width=True):
            st.markdown(f"[Click to grant access]({graph_client.build_admin_consent_url(redirect_uri)})")
        onboarded = tenant_store.list_tenants()
        st.caption("**Onboarded clients:**")
        if onboarded:
            for t in onboarded:
                st.caption(f"• {t['label']}")
        else:
            st.caption("None yet.")

    st.markdown("### 🎛️ Meeting Input")
    mode = st.radio(
        "Source", ["Upload recording/transcript", "Fetch from Teams meeting"], label_visibility="collapsed"
    )
    st.markdown("---")

    if mode == "Upload recording/transcript":
        uploaded = st.file_uploader("Audio (mp3/mp4/wav) or transcript (.txt/.vtt)")
        if uploaded and st.button("▶ Process meeting", use_container_width=True, type="primary"):
            with st.spinner("Uploading and processing..."):
                data = uploaded.read()
                name = uploaded.name
                s3_uri = aws_pipeline.upload_bytes(data, f"uploads/{name}")
                if name.lower().endswith(".vtt"):
                    vtt_text = data.decode("utf-8")
                    segments = graph_client.parse_vtt_segments(vtt_text)
                    text = graph_client.vtt_to_plain_text(vtt_text)
                elif name.lower().endswith(".txt"):
                    text = data.decode("utf-8")
                    segments = [{"speaker": None, "start": "00:00:00", "text": text}]
                else:
                    media_format = name.rsplit(".", 1)[-1].lower()
                    result = aws_pipeline.transcribe_audio(s3_uri, media_format=media_format)
                    text = result["text"]
                    segments = result["segments"]
                st.session_state.transcript = text
                st.session_state.segments = segments
                st.session_state.summary = aws_pipeline.summarize_transcript(text)
                st.session_state.chat_history = []
                st.session_state.speaker_colors = {}
    else:
        tenant_options = {t["label"]: t["tenant_id"] for t in tenant_store.list_tenants()}
        selected_tenant_id = None
        if tenant_options:
            selected_label = st.selectbox("Client", list(tenant_options.keys()))
            selected_tenant_id = tenant_options[selected_label]
        else:
            st.caption("No clients onboarded yet — use Client Onboarding above, or this falls back to the default tenant in .env.")
        meeting_id = st.text_input("Online meeting ID")
        if st.button("▶ Fetch & process", use_container_width=True, type="primary"):
            with st.spinner("Fetching from Teams and processing..."):
                result = bot_service.process_teams_meeting(config.ORGANIZER_UPN, meeting_id, selected_tenant_id)
                st.session_state.transcript = result["transcript"]
                st.session_state.segments = result["segments"]
                st.session_state.summary = result["summary"]
                st.session_state.recording_bytes = result.get("recording_bytes")
                st.session_state.chat_history = []
                st.session_state.speaker_colors = {}

    with st.expander("📅 Auto-Detected Meetings"):
        st.caption(
            "Detects meetings from the organizer's calendar automatically, and "
            "processes them once they've ended - no manual IDs needed. Live "
            "join isn't active yet (pending Microsoft's real-time media "
            "approval - see plan.md), so processing happens after the meeting ends."
        )
        scan_tenant_options = {t["label"]: t["tenant_id"] for t in tenant_store.list_tenants()}
        scan_tenant_id = None
        if scan_tenant_options:
            scan_label = st.selectbox("Client", list(scan_tenant_options.keys()), key="scan_client")
            scan_tenant_id = scan_tenant_options[scan_label]

        if "auto_scanned" not in st.session_state:
            with st.spinner("Checking calendar and browser-bot captures..."):
                scheduler_service.detect_new_meetings(config.ORGANIZER_UPN, scan_tenant_id)
                scheduler_service.process_due_meetings(scan_tenant_id)
                browser_bot_ingest.process_browser_bot_captures()
            st.session_state.auto_scanned = True

        if st.button("🔄 Check calendar now", use_container_width=True):
            with st.spinner("Checking calendar and browser-bot captures..."):
                new_meetings = scheduler_service.detect_new_meetings(config.ORGANIZER_UPN, scan_tenant_id)
                processed = scheduler_service.process_due_meetings(scan_tenant_id)
                bot_processed = browser_bot_ingest.process_browser_bot_captures()
                st.success(
                    f"{len(new_meetings)} new meeting(s) detected, {len(processed)} processed, "
                    f"{len(bot_processed)} browser-bot capture(s) processed."
                )

        tracked = meeting_store.list_meetings()
        if tracked:
            for m in sorted(tracked, key=lambda x: x["start"], reverse=True):
                status_icon = {"scheduled": "🕒", "processed": "✅", "failed": "⚠️"}.get(m["status"], "•")
                cols = st.columns([4, 1])
                cols[0].caption(f"{status_icon} **{m['subject']}** — {m['start'][:16].replace('T', ' ')} ({m['status']})")
                if m["status"] == "processed" and cols[1].button("View", key=f"view_{m['event_id']}"):
                    st.session_state.transcript = m["transcript"]
                    st.session_state.segments = m["segments"]
                    st.session_state.summary = m["summary"]
                    st.session_state.recording_bytes = None
                    st.session_state.chat_history = []
                    st.session_state.speaker_colors = {}
                    st.rerun()
        else:
            st.caption("No meetings tracked yet.")

        if not st.session_state.transcript and tracked:
            processed_meetings = [m for m in tracked if m["status"] == "processed"]
            if processed_meetings:
                latest = max(processed_meetings, key=lambda x: x["start"])
                st.session_state.transcript = latest["transcript"]
                st.session_state.segments = latest["segments"]
                st.session_state.summary = latest["summary"]
                st.session_state.recording_bytes = None
                st.session_state.chat_history = []
                st.session_state.speaker_colors = {}

if st.session_state.transcript:
    transcript = st.session_state.transcript
    segments = st.session_state.segments
    summary = st.session_state.summary or {}
    decisions = summary.get("decisions", [])
    action_items = summary.get("action_items", [])
    open_questions = summary.get("open_questions", [])

    st.markdown(
        f'<div class="mx-panel" style="margin-bottom:16px"><h4>📄 Overview</h4>'
        f'<p style="color:{INK_SECONDARY};font-size:14px;line-height:1.6;margin:0">'
        f'{summary.get("summary", "No summary generated.")}</p></div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("recording_bytes"):
        st.audio(st.session_state.recording_bytes)

    st.markdown(
        f'<div class="mx-stats">{len(transcript.split()):,} words &bull; '
        f"{len(decisions)} decisions &bull; {len(action_items)} action items &bull; "
        f"{len(open_questions)} open questions</div>",
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([1, 1])

    with col_left:
        tab_search, tab_highlights, tab_soundbites = st.tabs(["🔍 Smart Search", "🧵 Highlights", "🎧 Soundbites"])

        with tab_search:
            st.markdown('<div class="mx-panel">', unsafe_allow_html=True)
            quick_prompts = ["Decisions", "Action items", "Open questions", "Key topics"]
            chip_cols = st.columns(len(quick_prompts))
            quick_question = None
            for col, label in zip(chip_cols, quick_prompts):
                if col.button(label, key=f"chip_{label}", use_container_width=True):
                    quick_question = f"What were the {label.lower()} in this meeting?"

            for turn in st.session_state.chat_history:
                with st.chat_message(turn["role"]):
                    st.write(turn["content"])

            asked_question = st.chat_input("Ask about this meeting...")
            question = quick_question or asked_question
            if question:
                st.session_state.chat_history.append({"role": "user", "content": question})
                answer = aws_pipeline.answer_question(
                    transcript, question, st.session_state.chat_history[:-1]
                )
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        with tab_highlights:
            rows = "".join(comment_row(item.get("owner", "Unassigned"), "action item", item.get("task", "")) for item in action_items)
            rows += "".join(comment_row("Decision", "", d) for d in decisions)
            if not rows:
                rows = '<span class="mx-empty">No highlights yet — process a meeting to see decisions and action items here.</span>'
            st.markdown(f'<div class="mx-panel"><h4>Decisions &amp; Action Items</h4>{rows}</div>', unsafe_allow_html=True)

        with tab_soundbites:
            if open_questions:
                rows = "".join(comment_row("Open question", "", q) for q in open_questions)
            else:
                rows = '<span class="mx-empty">No open questions detected.</span>'
            st.markdown(f'<div class="mx-panel"><h4>Open Questions</h4>{rows}</div>', unsafe_allow_html=True)

    with col_right:
        if segments:
            rows = "".join(comment_row(seg["speaker"] or "Speaker", seg["start"], seg["text"]) for seg in segments)
        else:
            rows = f'<div class="mx-comment-body"><div class="text">{transcript}</div></div>'
        st.markdown(f'<div class="mx-panel"><h4>📝 Transcript</h4>{rows}</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="mx-panel"><h4>👋 Get started</h4>'
        "<p>No processed meetings yet. Once a tracked meeting finishes, its transcript, summary, "
        "decisions, action items, and chat will appear here automatically — or upload a "
        "recording/transcript from the sidebar to process one right now.</p></div>",
        unsafe_allow_html=True,
    )
