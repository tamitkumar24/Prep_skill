import os, json, random, sqlite3, urllib.request
from datetime import datetime, date
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from questions import QUESTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(HERE, ".env")):           # local secrets, never committed
    for line in open(os.path.join(HERE, ".env")):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1); os.environ.setdefault(k, v)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")
app.jinja_env.filters["j"] = json.loads
DB = "/tmp/prep.db" if os.environ.get("VERCEL") else os.path.join(HERE, "prep.db")

SUBJECTS = {"Mixed": "A shuffled round from every subject", "Python": "Output guessing and core behaviour",
            "DSA": "Complexity, structures, recursion", "SQL & DBMS": "Queries, keys, normal forms",
            "OOP": "Pillars, overriding, abstraction", "Web Dev": "HTTP, JavaScript, CSS",
            "Networks & OS": "Protocols, layers, deadlocks", "Machine Learning": "Fitting, metrics, basics",
            "Aptitude": "Speed, percentages, series"}
QUOTES = ["Every mock round you finish is one less surprise on the day.", "Confidence is just practice you've stopped counting.",
          "Slow is fine. Skipping is not.", "You don't need to know everything, only how to reason through it.",
          "A wrong answer today is a right answer on interview day.", "Small daily rounds beat one long weekend cram."]
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, category TEXT, level TEXT, type TEXT, text TEXT, code TEXT, options TEXT, answer TEXT, explanation TEXT);
CREATE TABLE IF NOT EXISTS interviews(id INTEGER PRIMARY KEY, user_id INT, category TEXT, level TEXT, qids TEXT, created TEXT, correct INT, total INT, score REAL);
CREATE TABLE IF NOT EXISTS answers(id INTEGER PRIMARY KEY, interview_id INT, question_id INT, picked TEXT, ok INT);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    con = sqlite3.connect(DB); con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM questions").fetchone():
        con.executemany("INSERT INTO questions(category,level,type,text,code,options,answer,explanation) VALUES(?,?,?,?,?,?,?,?)", QUESTIONS)
    con.commit(); con.close()
init_db()   # runs on import so hosting platforms get a ready database

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        return f(*a, **k) if "uid" in session else redirect(url_for("login"))
    return w

# ---------- AI tutor (Gemini REST API, optional) ----------
def ask_ai(msg, q=None, reveal=False):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        if q and reveal: return "Explanation: " + q["explanation"] + "\n\n(Add GEMINI_API_KEY to enable the full AI tutor.)"
        return "The AI tutor isn't connected yet. Add GEMINI_API_KEY to your .env file and restart. Meanwhile: re-read the question and eliminate options that are clearly wrong."
    ctx = ""
    if q:
        ctx = f"Interview question: {q['text']}\n{q['code']}\nOptions: {q['options']}\n"
        ctx += (f"The student already answered. You may reveal and explain the correct option(s) (indexes {q['answer']})."
                if reveal else "Do NOT reveal the correct option. Give a hint or teach the concept only.")
    body = {"system_instruction": {"parts": [{"text": "You are a friendly interview-prep tutor for CS students. Reply in simple English, under 150 words, with short code blocks when useful."}]},
            "contents": [{"role": "user", "parts": [{"text": ctx + "\nStudent: " + msg}]}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{os.environ.get('GEMINI_MODEL','gemini-2.5-flash')}:generateContent?key={key}"
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=25))["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return "The AI tutor couldn't respond just now. Check your API key or try again in a moment."

@app.route("/api/ai", methods=["POST"])
@login_required
def api_ai():
    d = request.get_json(force=True); q = None; reveal = False
    if d.get("qid"):
        q = db().execute("SELECT * FROM questions WHERE id=?", (int(d["qid"]),)).fetchone()
        reveal = bool(db().execute("SELECT 1 FROM answers a JOIN interviews i ON i.id=a.interview_id WHERE i.user_id=? AND a.question_id=?", (session["uid"], d["qid"])).fetchone())
    return jsonify(reply=ask_ai(str(d.get("message", ""))[:800], q, reveal))

# ---------- auth ----------
@app.route("/")
def home(): return redirect(url_for("dashboard" if "uid" in session else "login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        n, e, p = (request.form[k].strip() for k in ("name", "email", "password"))
        if len(p) < 6: flash("Password must be at least 6 characters.")
        else:
            try:
                db().execute("INSERT INTO users(name,email,password) VALUES(?,?,?)", (n, e.lower(), generate_password_hash(p)))
                db().commit(); flash("Account created. Log in to start practising."); return redirect(url_for("login"))
            except sqlite3.IntegrityError: flash("That email is already registered.")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),)).fetchone()
        if u and check_password_hash(u["password"], request.form["password"]):
            session.update(uid=u["id"], name=u["name"]); return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

# ---------- practice ----------
@app.route("/dashboard")
@login_required
def dashboard():
    rows = db().execute("SELECT * FROM interviews WHERE user_id=? AND score IS NOT NULL ORDER BY id DESC", (session["uid"],)).fetchall()
    avg = round(sum(r["score"] for r in rows) / len(rows)) if rows else None
    return render_template("dashboard.html", subjects=SUBJECTS, rows=rows[:4], total=len(rows), avg=avg, quote=QUOTES[date.today().toordinal() % len(QUOTES)])

@app.route("/start", methods=["POST"])
@login_required
def start():
    cat, level, n = request.form["category"], request.form["level"], int(request.form["count"])
    qs = db().execute("SELECT id, level FROM questions" + ("" if cat == "Mixed" else " WHERE category=?"), () if cat == "Mixed" else (cat,)).fetchall()
    random.shuffle(qs); qs.sort(key=lambda r: r["level"] != level)   # preferred difficulty first
    ids = [r["id"] for r in qs[:n]]; random.shuffle(ids)
    cur = db().execute("INSERT INTO interviews(user_id,category,level,qids,created,total) VALUES(?,?,?,?,?,?)",
                       (session["uid"], cat, level, ",".join(map(str, ids)), datetime.now().strftime("%d %b %Y, %H:%M"), len(ids)))
    db().commit(); return redirect(url_for("interview", iid=cur.lastrowid))

@app.route("/interview/<int:iid>", methods=["GET", "POST"])
@login_required
def interview(iid):
    iv = db().execute("SELECT * FROM interviews WHERE id=? AND user_id=?", (iid, session["uid"])).fetchone()
    if not iv: return redirect(url_for("dashboard"))
    ids = [int(x) for x in iv["qids"].split(",")]
    done = db().execute("SELECT COUNT(*) c FROM answers WHERE interview_id=?", (iid,)).fetchone()["c"]
    if done >= len(ids): return redirect(url_for("result", iid=iid))
    q = db().execute("SELECT * FROM questions WHERE id=?", (ids[done],)).fetchone()
    if request.method == "POST":
        picked = sorted(int(x) for x in request.form.getlist("opt"))
        if not picked: flash("Pick at least one option."); return redirect(url_for("interview", iid=iid))
        db().execute("INSERT INTO answers(interview_id,question_id,picked,ok) VALUES(?,?,?,?)", (iid, q["id"], json.dumps(picked), int(picked == json.loads(q["answer"]))))
        if done + 1 == len(ids):
            c = db().execute("SELECT SUM(ok) s FROM answers WHERE interview_id=?", (iid,)).fetchone()["s"]
            db().execute("UPDATE interviews SET correct=?, score=? WHERE id=?", (c, round(100 * c / len(ids)), iid))
        db().commit(); return redirect(url_for("interview", iid=iid))
    return render_template("interview.html", iv=iv, q=q, opts=json.loads(q["options"]), n=done + 1, total=len(ids))

@app.route("/result/<int:iid>")
@login_required
def result(iid):
    iv = db().execute("SELECT * FROM interviews WHERE id=? AND user_id=?", (iid, session["uid"])).fetchone()
    if not iv or iv["score"] is None: return redirect(url_for("dashboard"))
    ans = db().execute("SELECT a.*, q.text, q.code, q.options, q.answer, q.explanation, q.type FROM answers a JOIN questions q ON q.id=a.question_id WHERE interview_id=? ORDER BY a.id", (iid,)).fetchall()
    return render_template("result.html", iv=iv, ans=ans)

@app.route("/progress")
@login_required
def progress():
    rows = db().execute("SELECT * FROM interviews WHERE user_id=? AND score IS NOT NULL ORDER BY id", (session["uid"],)).fetchall()
    return render_template("progress.html", rows=rows)

@app.route("/doubts")
@login_required
def doubts(): return render_template("doubts.html")

if __name__ == "__main__":
    app.run(debug=True)
