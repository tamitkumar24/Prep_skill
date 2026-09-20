# PrepRoom – AI Interview Preparation Platform
Flask + SQLite. MCQ / MSQ / code-reading questions, 8 subjects + Mixed, AI tutor (Gemini).

## Run locally
    pip install flask scikit-learn
    python app.py
Put your keys in `.env` (copy `.env.example`). Without GEMINI_API_KEY the app still works; the AI tutor shows a setup message.

## Deploy on Vercel
1. Push to GitHub (.gitignore already hides .env and *.db).
2. Import repo in Vercel, add SECRET_KEY and GEMINI_API_KEY under Settings > Environment Variables.
3. Note: Vercel's disk is temporary, so accounts/history reset on cold starts. For permanent data use an external database.

## Add questions
Edit questions.py, delete prep.db, restart.
