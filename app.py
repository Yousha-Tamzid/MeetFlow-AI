import os, json, sqlite3
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

load_dotenv()
DB = Path("meetflow.db")
st.set_page_config(page_title="MeetFlow AI", page_icon="🎙️", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=Space+Grotesk:wght@600;700&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.stApp{background:linear-gradient(135deg,#0b1020,#101a2d 55%,#111827);color:#e8edf7}
h1,h2,h3{font-family:'Space Grotesk',sans-serif}
.block-container{max-width:1200px;padding-top:2rem}
.hero{padding:28px;border:1px solid #293650;border-radius:20px;background:linear-gradient(120deg,#17233c,#172b3e);margin-bottom:20px}
.hero p{color:#aab8ce}.pill{color:#8ee8d0;background:#203c54;padding:5px 10px;border-radius:30px}
</style>""", unsafe_allow_html=True)

def connect():
    c=sqlite3.connect(DB,check_same_thread=False); c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY,title TEXT,day TEXT,transcript TEXT,summary TEXT,decisions TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,meeting_id INTEGER,task TEXT,owner TEXT,due TEXT,priority TEXT,status TEXT,source TEXT)""")
    c.commit(); return c
conn=connect()

def client():
    key=os.getenv("GROQ_API_KEY","").strip()
    return Groq(api_key=key) if key else None

def generate_meeting_pdf(meeting, tasks):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("MeetFlow AI - Meeting Report", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Meeting:</b> {meeting['title']}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date:</b> {meeting['day']}", styles["Normal"]))
    story.append(Spacer(1, 15))

    story.append(Paragraph("Meeting Summary", styles["Heading2"]))
    story.append(Paragraph(meeting["summary"] or "No summary available.", styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Decisions", styles["Heading2"]))

    decisions = json.loads(meeting["decisions"] or "[]")

    if decisions:
        for decision in decisions:
            story.append(Paragraph(f"• {decision}", styles["BodyText"]))
    else:
        story.append(Paragraph("No decisions recorded.", styles["BodyText"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Action Items", styles["Heading2"]))

    table_data = [
        ["Task", "Owner", "Due date", "Priority", "Status"]
    ]

    for task in tasks:
        table_data.append([
            task["task"],
            task["owner"] or "Unassigned",
            task["due"] or "Not set",
            task["priority"],
            task["status"]
        ])

    if len(table_data) == 1:
        table_data.append(["No tasks", "-", "-", "-", "-"])

    table = Table(
        table_data,
        colWidths=[180, 75, 75, 65, 65],
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243B53")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.append(table)

    total = len(tasks)
    completed = sum(1 for task in tasks if task["status"] == "Done")

    story.append(Spacer(1, 15))
    story.append(Paragraph("Task Analytics", styles["Heading2"]))
    story.append(Paragraph(
        f"Total tasks: {total} | Completed: {completed} | "
        f"Pending: {total - completed}",
        styles["BodyText"]
    ))

    doc.build(story)

    buffer.seek(0)
    return buffer.getvalue()

def analyze(title, transcript):
    previous=conn.execute("SELECT title,summary FROM meetings ORDER BY id DESC LIMIT 5").fetchall()
    context="\n".join(f"{x['title']}: {x['summary']}" for x in previous) or "No previous meetings."
    
    prompt=f"""You are MeetFlow AI, an accurate meeting-to-execution assistant.

Analyze the meeting transcript carefully and return ONLY valid JSON.

Your responsibilities:
1. Extract every actionable task mentioned in the transcript.
2. Never skip an action item, even if it sounds like a small follow-up or review.
3. Create a separate task for each distinct action item.
4. Identify the correct owner from the transcript. If no owner is explicitly identified, use "Unassigned".
5. Extract deadlines accurately. Never guess missing dates. Use null if no deadline is mentioned.
6. Assign priority based on urgency and importance. Use High, Medium, or Low.
7. Include a short exact evidence quote from the transcript for every task.
8. Do not create duplicate tasks for the same action.
9. Keep decisions separate from tasks. A decision is not automatically a task unless someone must take action.
10. Do not invent tasks, owners, dates, or commitments.

Return this JSON structure:
{{
    "summary": "Short meeting summary",
    "decisions": ["Decision 1"],
    "tasks": [
        {{
            "task": "Specific actionable task",
            "owner": "Person name or Unassigned",
            "due_date": "YYYY-MM-DD or null",
            "priority": "High|Medium|Low",
            "source_quote": "Evidence from transcript"
        }}
    ],
    "conflicts": [
        {{
            "new_statement": "New statement",
            "previous_context": "Earlier commitment",
            "explanation": "Why they may conflict",
            "severity": "High|Medium|Low"
        }}
    ],
    "open_questions": ["Unresolved question"]
}}

Important task extraction rules:
- Extract tasks involving creating, completing, reviewing, testing, fixing, preparing, sending, checking, or delivering something.
- If a person says "I will..." or the team assigns an action to someone, create a task.
- If an action has no named owner, create it with owner "Unassigned".
- A task without a deadline must still be included.
- Preserve the meaning of the original action.
- Check the entire transcript from beginning to end before returning the JSON.
- Return an empty array only when no actionable tasks exist.
- Detect conflicts only when supported by previous meeting context.
- Convert every explicitly mentioned deadline into YYYY-MM-DD format.
- Today's date is {date.today().isoformat()}. If a deadline mentions a month and day but no year, use the next upcoming occurrence of that date.
- For example, "November 12" means "2026-11-12" when today's date is October 31, 2026.
- Never return null for a deadline that is clearly stated in the transcript. Return null only when no deadline is mentioned.

Meeting title: {title}

Previous meeting context:
{context}

Meeting transcript:
{transcript}"""

    c=client()
    if not c: return None,"Add GROQ_API_KEY in .env to enable AI analysis."
    try:
        r=c.chat.completions.create(model="openai/gpt-oss-120b",messages=[{"role":"user","content":prompt}],temperature=.2,response_format={"type":"json_object"})
        return json.loads(r.choices[0].message.content),None
    except Exception as e: return None,str(e)

def demo(transcript):
    lines=[x.strip(" -•") for x in transcript.splitlines() if x.strip()]
    actions=[x for x in lines if any(k in x.lower() for k in ["will ","must ","need to","action:","follow up","send ","prepare ","finish "])]
    decisions=[x for x in lines if any(k in x.lower() for k in ["decided","agree","approved","decision:"])]
    return {"summary":"Demo-mode extraction. Configure Groq for contextual AI analysis.","decisions":decisions[:8],
            "tasks":[{"task":x,"owner":"Unassigned","due_date":None,"priority":"Medium","source_quote":x} for x in actions[:12]],
            "conflicts":[],"open_questions":["Who owns each unassigned task?","What deadlines were agreed?"]}

st.markdown('<div class="hero"><span class="pill">VOICE-FIRST · AGENTIC WORKFLOW</span><h1 style="font-size:2.6rem;margin:12px 0">MeetFlow <span style="color:#68d9c0">AI</span></h1><p>Turn conversations into decisions, accountable tasks, and follow-through.</p></div>',unsafe_allow_html=True)
if "next_page" in st.session_state:
    st.session_state["workspace_page"] = st.session_state.pop("next_page")
page=st.sidebar.radio(
    "Workspace",
    ["New meeting", "Task board", "Meeting history", "How it works"],
    key="workspace_page"
)
st.sidebar.caption("Human review required before tasks are created.")
if page=="New meeting":
    st.subheader("Capture a meeting")
    title=st.text_input("Meeting title",placeholder="Product launch planning")
    audio=st.audio_input("Record meeting audio")
    transcript=st.text_area("Meeting transcript",height=200,placeholder="Paste transcript here, or transcribe your recording...")
    if audio is not None and st.button("🎧 Transcribe audio"):
        c=client()
        if not c: st.error("Add GROQ_API_KEY to .env for audio transcription.")
        else:
            try:
                import io
                result=c.audio.transcriptions.create(file=("meeting.wav",io.BytesIO(audio.getvalue()).read()),model="whisper-large-v3",response_format="text")
                st.session_state["transcribed"]=str(result); st.success("Transcription ready — paste it into the transcript field.")
                st.code(str(result)[:5000])
            except Exception as e: st.error(f"Transcription failed: {e}")
    if st.button("✨ Analyze meeting", type="primary"):
        if not title.strip():
            st.warning("Please enter a meeting title.")

        elif not transcript.strip():
            st.warning("Please provide a meeting transcript before starting AI analysis.")

        else:
            with st.spinner("Extracting decisions, tasks, and possible conflicts..."):
                result, error = analyze(title, transcript)

                if error:
                    st.warning(error + " Showing demo extraction.")
                    result = demo(transcript)

                st.session_state["result"] = result
                st.session_state["title"] = title
                st.session_state["transcript"] = transcript

    data = st.session_state.get("result")
    if data:
        st.divider(); st.subheader("Review the agent's analysis"); st.write(data.get("summary",""))
        a,b=st.columns(2)
        with a:
            st.markdown("**Decisions**")
            for x in data.get("decisions",[]): st.markdown("- "+x)
            st.markdown("**Open questions**")
            for x in data.get("open_questions",[]): st.markdown("- "+x)
        with b:
            st.markdown("**Potential conflicts**")
            if data.get("conflicts"):
                for x in data["conflicts"]: st.warning(x.get("explanation","Potential conflict"))
            else: st.success("No supported conflicts detected.")
        edited=[]
        st.markdown("**Proposed tasks — edit before approval**")
        for i,t in enumerate(data.get("tasks",[])):
            with st.expander(f"{i+1}. {t.get('task','Task')}",expanded=True):
                task=st.text_input("Task",t.get("task",""),key=f"t{i}")
                owner=st.text_input("Owner",t.get("owner") or "Unassigned",key=f"o{i}")
                due=st.text_input("Due date (YYYY-MM-DD)",str(t.get("due_date") or ""),key=f"d{i}")
                priority=st.selectbox("Priority",["High","Medium","Low"],index=["High","Medium","Low"].index(t.get("priority","Medium")) if t.get("priority") in ["High","Medium","Low"] else 1,key=f"p{i}")
                st.caption("Evidence: "+t.get("source_quote","Not provided"))
                edited.append((task,owner,due,priority,t.get("source_quote","")))
        if edited and st.button("✓ Approve and create tasks", type="primary"):
            existing = conn.execute(
                """
                SELECT 1 FROM meetings
                WHERE title = ? AND day = ? AND transcript = ?
                LIMIT 1
                """,
                (
                    st.session_state["title"],
                    date.today().isoformat(),
                    st.session_state["transcript"]
                )
            ).fetchone()

            if existing:
                st.warning("This meeting has already been saved.")
            else:
                cur = conn.execute(
                    """
                    INSERT INTO meetings(title, day, transcript, summary, decisions)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        st.session_state["title"],
                        date.today().isoformat(),
                        st.session_state["transcript"],
                        data.get("summary", ""),
                        json.dumps(data.get("decisions", []))
                    )
                )

                mid = cur.lastrowid

                for t in edited:
                    conn.execute(
                        """
                        INSERT INTO tasks(meeting_id, task, owner, due, priority, status, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (mid, *t[:4], "To do", t[4])
                    )

                conn.commit()
                st.session_state.pop("result", None)
                st.session_state["next_page"] = "Task board"
                st.success("Approved and saved.")
                st.rerun()
elif page == "Task board":
    st.subheader("Action board")

    all_rows = conn.execute(
        """
        SELECT tasks.*, meetings.title AS meeting_title
        FROM tasks
        LEFT JOIN meetings ON tasks.meeting_id = meetings.id
        ORDER BY tasks.id DESC
        """
    ).fetchall()

    meeting_titles = ["All meetings"] + sorted({
        r["meeting_title"] or "Unknown meeting" for r in all_rows
    })

    selected_meeting = st.selectbox(
        "Filter by meeting",
        meeting_titles
    )
    rows = [
        r for r in all_rows
        if selected_meeting == "All meetings"
        or (r["meeting_title"] or "Unknown meeting") == selected_meeting
    ]
    search_query = st.text_input(
        "Search tasks",
        placeholder="Type a task name..."
    )

    priority_filter = st.selectbox(
        "Filter by priority",
        ["All priorities", "High", "Medium", "Low"]
    )

    if search_query:
        rows = [
            r for r in rows
            if search_query.lower() in r["task"].lower()
        ]

    if priority_filter != "All priorities":
        rows = [
            r for r in rows
            if r["priority"] == priority_filter
        ]


    if not rows:
        st.info("No approved tasks yet. Analyze a meeting first.")
    else:
        df = pd.DataFrame([dict(x) for x in rows])
        total_tasks = len(df)
        todo_tasks = int((df["status"] == "To do").sum())
        in_progress_tasks = int((df["status"] == "In progress").sum())
        completed_tasks = int((df["status"] == "Done").sum())

        st.markdown("### Task Overview")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Total Tasks", total_tasks)
        col2.metric("To Do", todo_tasks)
        col3.metric("In Progress", in_progress_tasks)
        col4.metric("Completed", completed_tasks)

        completion = completed_tasks / total_tasks if total_tasks else 0

        st.markdown("**Overall Completion**")
        st.progress(completion)
        st.caption(f"{completion:.0%} of tasks completed")
        st.metric("Open tasks", int((df.status != "Done").sum()))

        for r in rows:
            with st.container(border=True):
                a, b, c = st.columns([4, 2, 2])

                a.markdown("**" + r["task"] + "**")
                a.caption(
                    f"Owner: {r['owner']} · Due: {r['due'] or 'Not set'}"
                )

                b.caption("Priority: " + r["priority"])

                status = c.selectbox(
                    "Status",
                    ["To do", "In progress", "Done"],
                    index=["To do", "In progress", "Done"].index(r["status"]),
                    key=f"s{r['id']}"
                )

                if status != r["status"]:
                    conn.execute(
                        "UPDATE tasks SET status=? WHERE id=?",
                        (status, r["id"])
                    )
                    conn.commit()
                    st.rerun()

                if c.button("🗑️ Delete task", key=f"d{r['id']}"):
                    conn.execute(
                        "DELETE FROM tasks WHERE id=?",
                        (r["id"],)
                    )
                    conn.commit()
                    st.success("Task deleted.")
                    st.rerun()
        st.download_button("Download CSV",df.to_csv(index=False).encode(),"meetflow_tasks.csv","text/csv")
elif page=="Meeting history":
    st.subheader("Meeting history")
    for m in conn.execute("SELECT * FROM meetings ORDER BY id DESC").fetchall():
        with st.expander(f"{m['title']} · {m['day']}"):
            st.write(m["summary"]); st.markdown("**Transcript**"); st.text(m["transcript"])
            st.markdown("**Decisions**")
            for x in json.loads(m["decisions"] or "[]"): st.markdown("- "+x)
            st.markdown("**Tasks created**")

            meeting_tasks = conn.execute(
                """
                SELECT task, owner, due, priority, status
                FROM tasks
                WHERE meeting_id = ?
                """,
                (m["id"],)
            ).fetchall()

            total = len(meeting_tasks)
            completed = sum(1 for t in meeting_tasks if t["status"] == "Done")
            in_progress = sum(1 for t in meeting_tasks if t["status"] == "In progress")
            pending = sum(1 for t in meeting_tasks if t["status"] == "To do")

            st.markdown("**Task Analytics**")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total", total)
            c2.metric("Completed", completed)
            c3.metric("In Progress", in_progress)
            c4.metric("To Do", pending)

            progress = completed / total if total else 0
            st.progress(progress)
            st.caption(f"{progress:.0%} tasks completed")

            if meeting_tasks:
                for task in meeting_tasks:
                    st.markdown(
                        f"- **{task['task']}** — Owner: {task['owner']} | "
                        f"Due: {task['due'] or 'Not set'} | "
                        f"Priority: {task['priority']} | Status: {task['status']}"
                    )
            else:
                st.caption("No tasks created for this meeting.")

            pdf_tasks = conn.execute(
                """
                SELECT task, owner, due, priority, status
                FROM tasks
                WHERE meeting_id = ?
                """,
                (m["id"],)
            ).fetchall()

            pdf_data = generate_meeting_pdf(m, pdf_tasks)

            safe_title = "".join(
                ch if ch.isalnum() else "_" for ch in m["title"]
            )

            st.download_button(
                label="📄 Download PDF Report",
                data=pdf_data,
                file_name=f"{safe_title}_report.pdf",
                mime="application/pdf",
                key=f"pdf_{m['id']}"
            )

            if st.button("🗑️ Delete this meeting", key=f"delete_meeting_{m['id']}"):
                conn.execute(
                    "DELETE FROM tasks WHERE meeting_id = ?",
                    (m["id"],)
                )
                conn.execute(
                    "DELETE FROM meetings WHERE id = ?",
                    (m["id"],)
                )
                conn.commit()
                st.success("Meeting deleted.")
                st.rerun()

                    
else:
    st.subheader("How MeetFlow AI works")
    st.markdown("""1. **Capture:** Record speech or paste a meeting transcript.
2. **Understand:** AI extracts summary, decisions, owners, deadlines, tasks, and open questions.
3. **Compare:** Previous meeting context is checked for possible contradictions.
4. **Approve:** A human edits and approves proposed tasks.
5. **Execute:** Track task status and export the task list.""")
    st.info("Audio and transcript data may be sent to Groq when AI features are enabled. Get consent before processing confidential meetings.")
    st.markdown("**Wispr Flow:** Use voice dictation with your coding assistant during development and capture a screenshot for the hackathon submission. The app also accepts spoken meeting audio.")
