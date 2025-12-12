# ==========================================================
#  LEARNIFY.AI — RENDER READY VERSION (FREE PLAN SAFE)
# ==========================================================

from flask import (
    Flask, render_template, request, redirect,
    session, flash, jsonify, make_response
)
from textblob import TextBlob
import requests, sqlite3, os, datetime, json, sys

# ==========================================================
# APP INIT
# ==========================================================
app = Flask(__name__)
app.secret_key = "learnify_secret_key"

app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "learnify.db")

# ==========================================================
# SOCKET.IO (SAFE FALLBACK FOR FREE RENDER PLAN)
# ==========================================================
from flask_socketio import SocketIO

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"     # important for free Render
)

# ==========================================================
# FIX COOKIE BUG
# ==========================================================
from werkzeug.wrappers import Response as WerkzeugResponse
_original_set_cookie = WerkzeugResponse.set_cookie

def patched_set_cookie(self, *args, **kwargs):
    kwargs.pop("partitioned", None)
    return _original_set_cookie(self, *args, **kwargs)

WerkzeugResponse.set_cookie = patched_set_cookie


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
        created_at TEXT,
        banned INTEGER DEFAULT 0
    )
    """)

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
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        topic TEXT,
        mood TEXT,
        created_at TEXT
    )
    """)

    # NEW TABLE FOR SHARING SYSTEM
    c.execute("""
    CREATE TABLE IF NOT EXISTS share_links(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        video TEXT,
        topic TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()

# ==========================================================
# MAINTENANCE MODE
# ==========================================================
@app.before_request
def check_maintenance():
    try:
        from admin.routes import load_settings
        settings = load_settings()
        if settings.get("maintenance") and session.get("user") != "admin":
            return render_template("maintenance.html")
    except:
        pass


# ==========================================================
# BASIC ROUTES
# ==========================================================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html", now=datetime.datetime.utcnow())


# ==========================================================
# SIGNUP
# ==========================================================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"].strip()
        e = request.form["email"].strip()
        p = request.form["password"].strip()
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        try:
            db = get_db()
            db.execute("""
                INSERT INTO users(username, email, password, created_at)
                VALUES (?, ?, ?, ?)
            """, (u, e, p, now))
            db.commit()
            return redirect("/login")
        except:
            return render_template("signup.html", error="Username or Email already exists!")

    return render_template("signup.html")


# ==========================================================
# LOGIN
# ==========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()

        if not user:
            return render_template("login.html", error="Invalid username or password.")

        if user["banned"] == 1:
            return render_template("login.html", error="Your account is banned.")

        session["user"] = user["username"]
        session["is_admin"] = (user["username"] == "admin")

        return redirect("/")

    return render_template("login.html")


# ==========================================================
# LOGOUT
# ==========================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ==========================================================
# FETCH YOUTUBE VIDEOS
# ==========================================================
def fetch_youtube_videos(q):
    try:
        url = (
            "https://www.googleapis.com/youtube/v3/search?"
            f"part=snippet&maxResults=6&q={q}&type=video&key=AIzaSyC-G8AaOVXnPKtrT4mM4ND1CMA4whCLELo"
        )
        res = requests.get(url).json()
        videos = []

        for v in res.get("items", []):
            vid = v["id"]["videoId"]
            title = v["snippet"]["title"]
            thumb = v["snippet"]["thumbnails"]["medium"]["url"]

            videos.append({"title": title, "thumbnail": thumb, "url": f"https://www.youtube.com/watch?v={vid}"})

        return videos

    except:
        return []


# ==========================================================
# RECOMMENDATION ENGINE
# ==========================================================
@app.route("/recommend", methods=["POST"])
def recommend():
    query = request.form["user_input"]

    pol = round(TextBlob(query).sentiment.polarity, 2)
    mood = "Excited" if pol >= 0.4 else "Confused" if pol <= -0.2 else "Neutral"

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    videos = fetch_youtube_videos(query + " tutorial")

    if "user" in session:
        username = session["user"]
        db = get_db()

        db.execute("""
            INSERT INTO feedback(user_query, topic, mood, sentiment, feedback, username, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (query, query, mood, pol, "", username, now))
        db.commit()

        db.execute("""
            INSERT INTO admin_logs(username, topic, mood, created_at)
            VALUES (?, ?, ?, ?)
        """, (username, query, mood, now))
        db.commit()

        # SAFE REALTIME UPDATE FOR FREE PLAN
        socketio.emit("analytics_update", {
            "total_users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "total_feedback": db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        })

    return render_template("recommend.html", query=query, mood=mood, sentiment=pol, videos=videos)


# ==========================================================
# ADMIN LOGIN
# ==========================================================
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin123":
            session["user"] = "admin"
            session["is_admin"] = True
            return redirect("/admin")

        return render_template("admin_login.html", error="Invalid admin credentials")

    return render_template("admin_login.html")


# ==========================================================
# SHARE SYSTEM
# ==========================================================
@app.route("/generate_share_link", methods=["POST"])
def generate_share_link():
    data = request.json
    video = data["video"]
    topic = data["topic"]

    unique = str(int(datetime.datetime.utcnow().timestamp()))

    # Auto-detect Render hostname
    host = request.host_url.rstrip("/")

    link = f"{host}/share/{unique}"

    db = get_db()
    db.execute(
        "INSERT INTO share_links(code, video, topic, created_at) VALUES (?, ?, ?, ?)",
        (unique, video, topic, datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    )
    db.commit()

    return jsonify({"link": link})


@app.route("/share/<code>")
def open_shared_page(code):
    db = get_db()
    row = db.execute("SELECT * FROM share_links WHERE code=?", (code,)).fetchone()

    if not row:
        return "Invalid shared link"

    return render_template("shared_view.html", video=row["video"], topic=row["topic"])


# ==========================================================
# ADMIN PANEL
# ==========================================================
from admin.routes import admin_bp
app.register_blueprint(admin_bp, url_prefix="/admin")


# ==========================================================
# RUN APP
# ==========================================================
if __name__ == "__main__":
    print("🚀 Learnify.AI Running...")
    socketio.run(app, debug=True, port=5050)
