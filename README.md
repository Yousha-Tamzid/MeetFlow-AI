# MeetFlow AI 🎙️
**A voice-first Agentic AI meeting-to-execution assistant.**

MeetFlow converts conversations into summaries, decisions, action items, owners, deadlines, and open questions. It compares new meetings with saved context to flag possible contradictions, then requires human approval before saving tasks.

## Features
- Record meeting audio in the app; transcribe with Groq Whisper (`whisper-large-v3`).
- Analyze transcripts with Groq `openai/gpt-oss-120b`.
- Extract decisions, tasks, owners, due dates, priorities, and evidence quotes.
- Compare against previous meetings for potential conflicts.
- Human-in-the-loop approval before task creation.
- Persistent SQLite meeting history and task board.
- CSV export.

## Run locally (Windows)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` and set `GROQ_API_KEY` from https://console.groq.com/keys, then:
```bash
streamlit run app.py
```

Without an API key, the app provides a clearly labeled demo extraction mode. Full AI analysis and audio transcription require the key.

## Demo
1. Open New meeting and enter a title.
2. Record a meeting or paste a transcript.
3. Transcribe audio if needed, then paste the transcript into the text box.
4. Analyze meeting; review decisions, conflicts, and proposed tasks.
5. Edit the owner/deadline and approve task creation.
6. Track tasks on Task board and export CSV.

## Wispr Flow hackathon evidence
Use Wispr Flow voice dictation while building/refining the project and capture your own screenshot as evidence. The app supports spoken meeting audio as its core input. Attach the actual screenshot in your submission; do not claim evidence you have not captured.

## Privacy and limitations
When enabled, audio and transcript content are sent to Groq for transcription/analysis. Obtain consent before processing confidential meetings. AI outputs can be wrong; review before approval. Conflict detection depends on saved context and is not guaranteed to catch every contradiction. This is a prototype, not a production project-management integration.

## Stack
Python, Streamlit, Groq API, Whisper, GPT-OSS, SQLite, Pandas.

## Future Improvements

- Improve AI-powered task extraction and deadline detection.
- Integrate calendar applications for better task scheduling.
- Add email notifications for upcoming deadlines.
- Enable team collaboration and task assignment.
- Support additional languages for multilingual meetings.

MeetFlow AI transforms meeting conversations into clear decisions, assigned tasks, and actionable next steps.