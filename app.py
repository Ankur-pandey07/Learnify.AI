# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from textblob import TextBlob
import requests, sqlite3, os, datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "learnify_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "learnify.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "avatars")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}
YOUTUBE_API_KEY = "AIzaSyC-G8AaOVXnPKtrT4mM4ND1CMA4whCLELo"

# ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------- DB INIT + MIGRATE --------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_query TEXT,
            topic TEXT,
            mood TEXT,
            sentiment REAL,
            feedback TEXT
        )''')
        conn.commit()

        # add username, created_at columns if missing
        c.execute("PRAGMA table_info(feedback)")
        columns = [r[1] for r in c.fetchall()]
        if "username" not in columns:
            try:
                c.execute("ALTER TABLE feedback ADD COLUMN username TEXT")
            except Exception:
                pass
        if "created_at" not in columns:
            try:
                c.execute("ALTER TABLE feedback ADD COLUMN created_at TEXT")
            except Exception:
                pass
        conn.commit()

init_db()

# -------------------- UTIL --------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# -------------------- YOUTUBE FETCH --------------------
def fetch_youtube_videos(query):
    try:
        q = requests.utils.requote_uri(query)
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=6&q={q}&type=video&key={YOUTUBE_API_KEY}"
        resp = requests.get(url, timeout=6)
        data = resp.json()
        items = data.get("items", [])
        videos = []
        for item in items:
            snippet = item.get("snippet", {})
            vidid = item.get("id", {}).get("videoId", "")
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
            videos.append({
                "title": snippet.get("title", "Untitled"),
                "thumbnail": thumb or "https://via.placeholder.com/320x180",
                "url": f"https://www.youtube.com/watch?v={vidid}" if vidid else "#"
            })
        return videos
    except Exception:
        return []

# -------------------- RESOURCES --------------------
def get_online_resources(topic):
    topic = (topic or "programming").lower()
    resources = {
        "programming": [
            {"title":"W3Schools","url":"https://www.w3schools.com","description":"Beginner-friendly programming tutorials."},
            {"title":"GeeksForGeeks","url":"https://www.geeksforgeeks.org","description":"Articles, problems and explanations."},
            {"title":"FreeCodeCamp","url":"https://www.freecodecamp.org","description":"Project-based learning."},
            {"title":"MDN Web Docs","url":"https://developer.mozilla.org","description":"Official web docs."},
            {"title":"Coursera","url":"https://www.coursera.org","description":"University courses."},
            {"title":"Udemy","url":"https://www.udemy.com","description":"Paid & free courses."}
        ],
        "ai": [
            {"title":"OpenAI Docs","url":"https://platform.openai.com/docs","description":"API & modern AI docs."},
            {"title":"Google AI","url":"https://ai.google/education/","description":"Google AI resources."},
            {"title":"MIT OCW - AI","url":"https://ocw.mit.edu","description":"MIT course materials."},
            {"title":"Fast.ai","url":"https://www.fast.ai","description":"Practical deep learning."},
            {"title":"IBM AI","url":"https://www.ibm.com/training","description":"Enterprise AI training."},
            {"title":"Simplilearn AI","url":"https://www.simplilearn.com/artificial-intelligence-basics-article","description":"Beginner guides."}
        ],
        "ml": [
            {"title":"Kaggle Learn","url":"https://www.kaggle.com/learn","description":"Hands-on ML mini-courses."},
            {"title":"Andrew Ng ML","url":"https://www.coursera.org/learn/machine-learning","description":"Classic ML course."},
            {"title":"Scikit-Learn","url":"https://scikit-learn.org","description":"ML algorithms & examples."},
            {"title":"TensorFlow","url":"https://www.tensorflow.org/learn","description":"TF tutorials."},
            {"title":"Fast.ai","url":"https://www.fast.ai","description":"Deep learning for coders."},
            {"title":"TutorialsPoint ML","url":"https://www.tutorialspoint.com/machine_learning/index.htm","description":"Practical guides."}
        ],
        "cloud": [
            {"title":"AWS Training","url":"https://aws.amazon.com/training/","description":"AWS official training."},
            {"title":"Azure Learn","url":"https://learn.microsoft.com/en-us/azure/","description":"Microsoft Azure docs."},
            {"title":"Google Cloud","url":"https://cloud.google.com/learn","description":"Google Cloud training."},
            {"title":"Kubernetes","url":"https://kubernetes.io/docs/","description":"Orchestration docs."},
            {"title":"Cloud Academy","url":"https://cloudacademy.com","description":"Hands-on labs."},
            {"title":"IBM Cloud","url":"https://www.ibm.com/training/cloud","description":"Cloud courses."}
        ],
        "data science": [
            {"title":"Kaggle","url":"https://www.kaggle.com/learn","description":"Data science learning."},
            {"title":"DataCamp","url":"https://www.datacamp.com","description":"Interactive DS learning."},
            {"title":"Coursera DS","url":"https://www.coursera.org/specializations/data-science","description":"Specializations."},
            {"title":"Harvard DS","url":"https://online-learning.harvard.edu/subject/data-science","description":"Harvard material."},
            {"title":"Analytics Vidhya","url":"https://www.analyticsvidhya.com","description":"Practical articles."},
            {"title":"Towards Data Science","url":"https://towardsdatascience.com","description":"Blogs & guides."}
        ]
    }
    return resources.get(topic, resources["programming"])

# -------------------- AUTH --------------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)", (username,email,password))
                conn.commit()
                flash("Account created successfully!","success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username or Email already exists!","error")
                return redirect(url_for("signup"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (username,password))
            user = c.fetchone()
        if user:
            session["user"] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username/password","error")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))

# -------------------- HOME --------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------------------- RECOMMEND --------------------
@app.route("/recommend", methods=["POST"])
def recommend():
    user_input = request.form.get("user_input", "")
    sentiment = TextBlob(user_input).sentiment.polarity
    sentiment_clean = float(f"{sentiment:.2f}") if sentiment is not None else 0.0

    if sentiment_clean < -0.1:
        mood = "confused"
    elif sentiment_clean < 0.3:
        mood = "neutral"
    else:
        mood = "excited"

    topic = "general"
    for key in ["ai", "ml", "python", "cloud", "programming", "data science"]:
        if key in user_input.lower():
            topic = key
            break

    videos = fetch_youtube_videos(user_input + " tutorial")
    online_resources = get_online_resources(topic)

    # ensure keys exist
    for v in videos:
        v.setdefault("title","No title")
        v.setdefault("thumbnail","https://via.placeholder.com/320x180")
        v.setdefault("url","#")
    for r in online_resources:
        r.setdefault("title","Untitled")
        r.setdefault("description","No description")
        r.setdefault("url","#")

    username = session.get("user")
    created_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO feedback (user_query, topic, mood, sentiment, username, created_at) VALUES (?,?,?,?,?,?)",
                      (user_input, topic, mood, sentiment_clean, username, created_at))
        except sqlite3.OperationalError:
            c.execute("INSERT INTO feedback (user_query, topic, mood, sentiment) VALUES (?,?,?,?)",
                      (user_input, topic, mood, sentiment_clean))
        conn.commit()

    return render_template("recommend.html",
                           query=user_input,
                           mood=mood,
                           sentiment=sentiment_clean,
                           topic=topic.title(),
                           videos=videos,
                           online_resources=online_resources)

# -------------------- SUBMIT FEEDBACK --------------------
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    user_query = request.form.get("query")
    rating = request.form.get("rating", "0")
    feedback_text = request.form.get("feedback_text", "")
    username = session.get("user")
    full_feedback = f"{rating} Stars - {feedback_text}"

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if username:
            c.execute("""SELECT id FROM feedback WHERE username = ? AND user_query = ? ORDER BY id DESC LIMIT 1""", (username, user_query))
        else:
            c.execute("""SELECT id FROM feedback WHERE user_query = ? ORDER BY id DESC LIMIT 1""", (user_query,))
        row = c.fetchone()
        if row:
            last_id = row[0]
            c.execute("UPDATE feedback SET feedback = ? WHERE id = ?", (full_feedback, last_id))
        conn.commit()

    return render_template("thankyou.html", rating=rating, feedback_text=feedback_text)

# -------------------- AVATAR UPLOAD --------------------
@app.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    if "user" not in session:
        flash("Login required to upload avatar.")
        return redirect(url_for("login"))

    if "avatar" not in request.files:
        flash("No file part.")
        return redirect(url_for("dashboard"))

    file = request.files["avatar"]
    if file.filename == "":
        flash("No selected file.")
        return redirect(url_for("dashboard"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # store as username.ext
        ext = filename.rsplit(".", 1)[1].lower()
        username = session["user"]
        save_name = f"{secure_filename(username)}.{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, save_name)
        file.save(save_path)
        flash("Avatar uploaded.", "success")
        return redirect(url_for("dashboard"))
    else:
        flash("Invalid file type. Allowed: png,jpg,jpeg,gif")
        return redirect(url_for("dashboard"))

# serve avatar (not necessary, static will serve, but keep convenience)
@app.route("/avatars/<filename>")
def avatars(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# -------------------- DASHBOARD --------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Login required!")
        return redirect(url_for("login"))

    username = session["user"]

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # fetch user-specific history (latest first)
        c.execute("""SELECT user_query, topic, mood, sentiment, feedback, username, created_at
                     FROM feedback WHERE username = ? ORDER BY datetime(created_at) DESC""", (username,))
        history_rows = c.fetchall()

        # counts
        c.execute("SELECT topic, COUNT(*) FROM feedback WHERE username = ? GROUP BY topic", (username,))
        topic_counts = dict(c.fetchall())

        c.execute("SELECT mood, COUNT(*) FROM feedback WHERE username = ? GROUP BY mood", (username,))
        mood_counts = dict(c.fetchall())

        # weekly activity last 7 days
        c.execute("""SELECT date(created_at) as d, COUNT(*) as cnt
                     FROM feedback
                     WHERE username = ? AND date(created_at) >= date('now','-6 days')
                     GROUP BY date(created_at)
                     ORDER BY date(created_at) ASC""", (username,))
        weekly = dict(c.fetchall())

    # clean
    topic_data = { str(k or "Unknown"): int(v or 0) for k, v in topic_counts.items() }
    mood_data  = { str(k or "Unknown"): int(v or 0) for k, v in mood_counts.items() }

    # weekly list (7 days)
    weekly_activity = []
    for i in range(6, -1, -1):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        weekly_activity.append({"day": d[-5:], "count": int(weekly.get(d, 0))})

    # insights
    top_topic = max(topic_data, key=lambda k: topic_data[k]) if topic_data else "None"
    top_mood  = max(mood_data, key=lambda k: mood_data[k]) if mood_data else "None"
    total_recs = sum(topic_data.values())
    # avg sentiment
    avg_sentiment = 0.0
    s_count = 0
    for r in history_rows:
        try:
            if r["sentiment"] is not None:
                avg_sentiment += float(r["sentiment"])
                s_count += 1
        except:
            pass
    avg_sentiment = round((avg_sentiment / s_count), 2) if s_count > 0 else 0.0

    suggest_map = {
        "ai":"Try hands-on AI projects (Fast.ai, Kaggle).",
        "ml":"Build a small ML project using scikit-learn.",
        "python":"Practice with mini-projects and data manipulation.",
        "cloud":"Try a free AWS/Azure quickstart tutorial.",
        "programming":"Solve coding problems (GFG/LeetCode).",
        "data science":"Try Kaggle projects and EDA."
    }
    suggest_next = suggest_map.get(top_topic.lower(), "Explore high-quality beginner projects.") if isinstance(top_topic, str) else "Explore projects."

    # achievements
    num_queries = len(history_rows)
    achievements = []
    if num_queries >= 1: achievements.append("First Query ✅")
    if num_queries >= 5: achievements.append("Active Learner 🔥")
    if num_queries >= 15: achievements.append("Consistent Learner ⭐")
    if total_recs >= 20: achievements.append("Power User 🏆")

    # prepare history list
    history = []
    for r in history_rows:
        history.append({
            "user_query": r["user_query"],
            "topic": r["topic"],
            "mood": r["mood"],
            "sentiment": r["sentiment"],
            "feedback": r["feedback"],
            "created_at": r["created_at"] or ""
        })

    insights = {
        "top_topic": top_topic,
        "top_mood": top_mood,
        "avg_sentiment": avg_sentiment,
        "suggest_next": suggest_next,
        "recommendation_count": total_recs
    }

    # avatar url if exists
    avatar_url = None
    for ext in ["png","jpg","jpeg","gif"]:
        candidate = os.path.join(UPLOAD_FOLDER, f"{secure_filename(username)}.{ext}")
        if os.path.exists(candidate):
            avatar_url = url_for('static', filename=f"avatars/{secure_filename(username)}.{ext}")
            break

    return render_template("dashboard.html",
                           user=username,
                           history=history,
                           topic_data=topic_data,
                           mood_data=mood_data,
                           insights=insights,
                           weekly_activity=weekly_activity,
                           achievements=achievements,
                           avatar_url=avatar_url)

# -------------------- THANKYOU --------------------
@app.route("/thankyou")
def thankyou_get():
    return render_template("thankyou.html")
@app.route("/recommend", methods=["GET"])
def recommend_get():
    return redirect("/")

@app.route("/about")
def about():
    return render_template("about.html")


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True, port=5050)
