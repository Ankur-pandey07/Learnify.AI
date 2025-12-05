# ==========================================================
#  LEARNIFY.AI — FULL PRO VERSION (XP + Achievements + Charts)
# ==========================================================

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, send_from_directory
)
from textblob import TextBlob
import requests, sqlite3, os, datetime, json
from werkzeug.utils import secure_filename
from functools import wraps

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------
app = Flask(__name__)
app.secret_key = "learnify_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "learnify.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "avatars")
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif"}
YOUTUBE_API_KEY = "AIzaSyC-G8AaOVXnPKtrT4mM4ND1CMA4whCLELo"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ==========================================================
# AI HELPERS (AUTO LEVEL, CATEGORY, INTENT)
# ==========================================================
def auto_detect_level(text):
    t = text.lower()
    if any(k in t for k in ["basic", "intro", "fundamental", "beginner"]):
        return "Basics"
    if any(k in t for k in ["intermediate", "mid"]):
        return "Intermediate"
    if any(k in t for k in ["project", "hands-on", "build"]):
        return "Projects"
    if any(k in t for k in ["advanced", "expert", "deep"]):
        return "Advanced"
    return "Beginner"

def auto_detect_category(text):
    t = text.lower()
    if any(k in t for k in ["ai", "machine learning"]): return "AI"
    if "python" in t: return "Python"
    if any(k in t for k in ["html","css","javascript","react"]): return "Web"
    if "cloud" in t or "aws" in t: return "Cloud"
    if any(k in t for k in ["dsa", "algorithm"]): return "DSA"
    return "Programming"

def auto_detect_platform(text):
    t = text.lower()
    if "udemy" in t: return "Udemy"
    if "coursera" in t: return "Coursera"
    if "google" in t: return "Google"
    if "youtube" in t or "youtu" in t: return "YouTube"
    return "Unknown"

def analyze_query(text):
    t = text.lower()
    intent = "learn"
    if "project" in t: intent = "projects"
    elif "roadmap" in t: intent = "roadmap"
    elif "course" in t: intent = "course"

    level = "Beginner"
    if "intermediate" in t: level = "Intermediate"
    if "advanced" in t: level = "Advanced"

    topic = t.split()[-1] if len(t) else "programming"
    return {"topic": topic, "intent": intent, "level": level}

def compute_score(title, desc, user_level, user_intent):
    text = (title + " " + desc).lower()
    score = 0

    # Intent score
    if user_intent == "projects" and "project" in text: score += 30
    if user_intent == "course" and "course" in text: score += 20

    # Level score
    if user_level == "Beginner" and "beginner" in text: score += 20
    if user_level == "Intermediate" and "intermediate" in text: score += 20
    if user_level == "Advanced" and "advanced" in text: score += 20

    return score + min(len(text.split()), 20)

# ==========================================================
# DATABASE
# ==========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_query TEXT,
        topic TEXT,
        mood TEXT,
        sentiment REAL,
        feedback TEXT,
        username TEXT,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS roadmap_progress(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        topic TEXT,
        completed_json TEXT,
        xp INTEGER,
        updated_at TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

# ==========================================================
# AUTH
# ==========================================================
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"].strip()
        e = request.form["email"].strip()
        p = request.form["password"].strip()
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        try:
            db = get_db()
            db.execute("INSERT INTO users(username,email,password,created_at) VALUES(?,?,?,?)",
                       (u,e,p,now))
            db.commit()
            flash("Account Created!", "success")
            return redirect("/login")
        except:
            flash("Username or Email already exists!", "error")
            return redirect("/signup")

    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p)).fetchone()

        if user:
            session["user"] = u
            return redirect("/")
        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ==========================================================
# HOME
# ==========================================================
@app.route("/")
def home():
    return render_template("index.html")

# ==========================================================
# YOUTUBE API
# ==========================================================
def fetch_youtube_videos(q):
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/search?"
            f"part=snippet&maxResults=6&q={q}&type=video&key={YOUTUBE_API_KEY}"
        )
        res = requests.get(url).json()

        videos = []
        for v in res.get("items", []):
            vid = v["id"].get("videoId")
            title = v["snippet"].get("title")
            thumb = v["snippet"]["thumbnails"]["medium"]["url"]

            videos.append({
                "title": title,
                "thumbnail": thumb,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "level": auto_detect_level(title),
                "category": auto_detect_category(title),
                "platform": "YouTube"
            })
        return videos
    except:
        return []

# ==========================================================
# ONLINE RESOURCES (STATIC)
# ==========================================================
def get_online_resources(topic):
    topic = topic.lower()
    data = {
        "python": [
            {"title":"Python Basics - W3Schools","url":"https://w3schools.com","description":"Learn Python basics"},
            {"title":"Python Projects","url":"https://freecodecamp.org","description":"Hands-on Python projects"},
        ],
        "ai": [
            {"title":"Google AI","url":"https://ai.google","description":"AI basics & ML training"},
            {"title":"DeepLearning.AI","url":"https://deeplearning.ai","description":"Neural network courses"},
        ],
        "programming": [
            {"title":"GeeksForGeeks","url":"https://geeksforgeeks.org","description":"Programming & DSA"},
            {"title":"FreeCodeCamp","url":"https://freecodecamp.org","description":"Full stack + projects"},
        ]
    }
    R = data.get(topic, data["programming"])

    for r in R:
        txt = r["title"] + " " + r["description"]
        r["level"] = auto_detect_level(txt)
        r["category"] = auto_detect_category(txt)
        r["platform"] = auto_detect_platform(txt)
    return R

# ==========================================================
# RECOMMENDATION ENGINE
# ==========================================================
@app.route("/recommend", methods=["POST"])
def recommend():
    user_input = request.form["user_input"]
    sentiment = float(f"{TextBlob(user_input).sentiment.polarity:.2f}")

    if sentiment < -0.1: mood = "confused"
    elif sentiment < 0.3: mood = "neutral"
    else: mood = "excited"

    analysis = analyze_query(user_input)
    topic = analysis["topic"]

    online = get_online_resources(topic)
    videos = fetch_youtube_videos(topic + " tutorial")

    # AI Scoring
    for r in online:
        r["score"] = compute_score(r["title"], r["description"], analysis["level"], analysis["intent"])
    for v in videos:
        v["score"] = compute_score(v["title"], v["title"], analysis["level"], analysis["intent"])

    online = sorted(online, key=lambda x: x["score"], reverse=True)
    videos = sorted(videos, key=lambda x: x["score"], reverse=True)

    # Save feedback log
    if "user" in session:
        db = get_db()
        db.execute("""
        INSERT INTO feedback(user_query, topic, mood, sentiment, username, created_at)
        VALUES(?,?,?,?,?,?)
        """, (user_input, topic, mood, sentiment, session["user"],
              datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()

    return render_template("recommend.html",
                           query=user_input, topic=topic.title(),
                           mood=mood, sentiment=sentiment,
                           online_resources=online,
                           videos=videos)

# ==========================================================
# DASHBOARD
# ==========================================================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]
    db = get_db()
    rows = db.execute("""
        SELECT * FROM feedback WHERE username=?
        ORDER BY datetime(created_at) DESC
    """, (username,)).fetchall()

    # ------------------------
    # EMPTY USER → SAFE PAGE
    # ------------------------
    if not rows:
        return render_template("dashboard.html",
            user=username,
            history=[],
            insights={"top_topic":"None","top_mood":"None","avg_sentiment":0},
            topic_data={}, mood_data={}, sentiment_data=[],
            weekly_activity=[], achievements=[], avatar_url=None
        )

    # ------------------------
    # PREPARE DICTS
    # ------------------------
    topic_data = {}
    mood_data = {}
    sentiment_list = []

    for r in rows:
        t = r["topic"] or "Unknown"
        m = r["mood"] or "Neutral"
        s = float(r["sentiment"])

        topic_data[t] = topic_data.get(t, 0) + 1
        mood_data[m] = mood_data.get(m, 0) + 1
        sentiment_list.append(s)

    # ------------------------
    # INSIGHTS
    # ------------------------
    insights = {
        "top_topic": max(topic_data, key=topic_data.get),
        "top_mood": max(mood_data, key=mood_data.get),
        "avg_sentiment": round(sum(sentiment_list) / len(sentiment_list), 2)
    }

    # ------------------------
    # WEEKLY ACTIVITY
    # ------------------------
    import datetime
    weekdays = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    weekly = {d:0 for d in weekdays}

    for r in rows:
        dt = datetime.datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
        weekly[weekdays[dt.weekday()]] += 1

    weekly_activity = [{"day": d, "count": weekly[d]} for d in weekdays]

    # ------------------------
    # ACHIEVEMENTS
    # ------------------------
    achievements = []
    if len(rows) >= 1: achievements.append("First Step")
    if len(rows) >= 5: achievements.append("Learner Lv.1")
    if len(rows) >= 15: achievements.append("Explorer Lv.2")

    # ------------------------
    # AVATAR CHECK ✔️ (Important Fix)
    # ------------------------
    avatar_path = None
    for ext in ["png", "jpg", "jpeg"]:
        f = f"{username}.{ext}"
        check_path = os.path.join(UPLOAD_FOLDER, f)
        if os.path.exists(check_path):
            avatar_path = f"/avatars/{f}"
            break

    # ------------------------
    # RENDER TEMPLATE
    # ------------------------
    return render_template(
        "dashboard.html",
        user=username,
        history=rows,
        insights=insights,
        topic_data=topic_data,
        mood_data=mood_data,
        sentiment_data=sentiment_list,  # ✔️ FIXED
        weekly_activity=weekly_activity,
        achievements=achievements,
    )
 # ----------------------------------------------------------
# AVATAR UPLOAD
# ----------------------------------------------------------
@app.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    if "user" not in session:
        flash("Login required")
        return redirect(url_for("login"))

    file = request.files.get("avatar")
    if not file or file.filename.strip() == "":
        flash("No file selected")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Invalid image type")
        return redirect(url_for("dashboard"))

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{secure_filename(session['user'])}.{ext}"

    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)

    return redirect(url_for("dashboard"))

# ----------------------------------------------------------
# RUN
# ----------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5050)
