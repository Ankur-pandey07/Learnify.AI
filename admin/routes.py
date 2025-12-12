from flask import Blueprint, render_template, session, redirect, request, jsonify, flash
import sqlite3, os, json

admin_bp = Blueprint("admin", __name__, template_folder="templates")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "learnify.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    with open(SETTINGS_PATH, "r") as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=4)

# ========================
# ADMIN DASHBOARD
# ========================
@admin_bp.route("/")
def admin_home():
    if session.get("user") != "admin":
        return "Access Denied!"

    db = get_db()

    # BASIC STATS
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_feedback = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    # TOPIC ANALYTICS
    rows = db.execute("SELECT topic FROM feedback").fetchall()
    topic_data = {}
    for r in rows:
        t = r["topic"]
        topic_data[t] = topic_data.get(t, 0) + 1

    # DAILY RECOMMENDATIONS (FOR LINE CHART)
    daily_rows = db.execute("""
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
        FROM feedback 
        GROUP BY day 
        ORDER BY day ASC
    """).fetchall()

    daily_labels = [r["day"] for r in daily_rows]
    daily_values = [r["total"] for r in daily_rows]

    # MOOD STATISTICS (FOR BAR CHART + RADAR)
    mood_rows = db.execute("""
        SELECT mood, COUNT(*) AS total 
        FROM feedback GROUP BY mood
    """).fetchall()

    mood_labels = [r["mood"] for r in mood_rows]
    mood_values = [r["total"] for r in mood_rows]

    return render_template(
        "admin.html",   # <-- IMPORTANT (USE dashboard file)
        total_users=total_users,
        total_feedback=total_feedback,
        topic_data=topic_data,
        daily_labels=daily_labels,
        daily_values=daily_values,
        mood_labels=mood_labels,
        mood_values=mood_values
    )



# ========================
# USERS PAGE
# ========================
@admin_bp.route("/users")
def admin_users():
    if session.get("user") != "admin":
        return "Access Denied!"

    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    return render_template("admin_users.html", users=rows)


# Delete User
@admin_bp.route("/delete_user", methods=["DELETE"])
def delete_user():
    if session.get("user") != "admin":
        return jsonify({"success": False, "message": "Unauthorized"})

    user_id = request.args.get("id")

    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()

    db.execute("DELETE FROM feedback WHERE username=(SELECT username FROM users WHERE id=?)", (user_id,))
    db.commit()

    return jsonify({"success": True})


# Update User
@admin_bp.route("/update_user", methods=["POST"])
def update_user():
    if session.get("user") != "admin":
        return jsonify({"success": False})

    data = request.get_json()
    user_id = request.args.get("id")

    db = get_db()
    db.execute("""
        UPDATE users SET username=?, email=? WHERE id=?
    """, (data["username"], data["email"], user_id))
    db.commit()

    return jsonify({"success": True})


# ========================
# USER FEEDBACK PAGE
# ========================
@admin_bp.route("/user/<int:user_id>/feedback")
def user_feedback(user_id):
    if session.get("user") != "admin":
        return "Access Denied!"

    db = get_db()

    user = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return "User not found"

    rows = db.execute("SELECT * FROM feedback WHERE username=? ORDER BY id DESC",
                      (user["username"],)).fetchall()

    return render_template("admin_user_feedback.html",
                           user=user["username"],
                           rows=rows)


# ========================
# FEEDBACK MANAGEMENT
# ========================
@admin_bp.route("/feedback")
def admin_feedback():
    if session.get("user") != "admin":
        return "Access Denied!"

    db = get_db()
    rows = db.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    return render_template("admin_feedback.html", feedbacks=rows)


# DELETE FEEDBACK
@admin_bp.route("/delete_feedback", methods=["DELETE"])
def delete_feedback():
    if session.get("user") != "admin":
        return jsonify({"success": False})

    f_id = request.args.get("id")

    db = get_db()
    db.execute("DELETE FROM feedback WHERE id=?", (f_id,))
    db.commit()

    return jsonify({"success": True})


# UPDATE FEEDBACK
@admin_bp.route("/update_feedback", methods=["POST"])
def update_feedback():
    if session.get("user") != "admin":
        return jsonify({"success": False})

    data = request.get_json()

    db = get_db()
    db.execute("""
        UPDATE feedback SET feedback=?, topic=?, mood=? WHERE id=?
    """, (data["feedback"], data["topic"], data["mood"], data["id"]))
    db.commit()

    return jsonify({"success": True})


# ========================
# ADMIN SETTINGS PAGE
# ========================
@admin_bp.route("/settings", methods=["GET", "POST"])
def admin_settings():
    if session.get("user") != "admin":
        return "Access Denied!"

    settings = load_settings()

    if request.method == "POST":
        settings["announcement"] = request.form.get("announcement", "")
        save_settings(settings)
        return redirect("/admin/settings")

    return render_template("admin_settings.html", announcement=settings["announcement"])

@admin_bp.route("/toggle_maintenance")
def toggle_maintenance():
    if session.get("user") != "admin":
        return "Access Denied!"

    settings = load_settings()
    settings["maintenance"] = not settings["maintenance"]
    save_settings(settings)

    return redirect("/admin/settings")

@admin_bp.route("/add_notification", methods=["POST"])
def add_notification():
    if session.get("user") != "admin":
        return "Access Denied!"

    note = request.form.get("notification", "")
    settings = load_settings()
    settings["notifications"].append(note)
    save_settings(settings)

    return redirect("/admin/settings")

@admin_bp.route("/ban_user/<int:uid>")
def ban_user(uid):
    db = get_db()
    db.execute("UPDATE users SET banned=1 WHERE id=?", (uid,))
    db.commit()
    return redirect("/admin/users")


@admin_bp.route("/unban_user/<int:uid>")
def unban_user(uid):
    db = get_db()
    db.execute("UPDATE users SET banned=0 WHERE id=?", (uid,))
    db.commit()
    return redirect("/admin/users")

@admin_bp.route("/analytics")
def admin_analytics():
    db = get_db()

    # -------- TOPIC COUNTS --------
    rows = db.execute("SELECT topic FROM feedback").fetchall()
    topic_data = {}

    for r in rows:
        t = r["topic"]
        if t and t.strip():
            topic_data[t] = topic_data.get(t, 0) + 1

    # -------- MOOD COUNTS --------
    mood_count = {"Excited": 0, "Neutral": 0, "Confused": 0}

    mood_rows = db.execute("SELECT mood FROM feedback").fetchall()
    for r in mood_rows:
        m = r["mood"]
        if m in mood_count:
            mood_count[m] += 1

    mood_labels = list(mood_count.keys())
    mood_values = list(mood_count.values())

    # -------- SAFE DAILY DUMMY DATA --------
    daily_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    daily_values = [12, 18, 25, 30, 22, 40, 55]

    # -------- DEBUG (INSIDE FUNCTION — CORRECT!) --------
    rows = db.execute("SELECT id, user_query, topic, mood FROM feedback").fetchall()
    print("\n========== FEEDBACK TABLE DEBUG ==========")
    for r in rows:
        print(dict(r))
    print("===========================================\n")

    # -------- RETURN --------
    return render_template(
        "admin_analytics.html",
        topic_data=topic_data,
        mood_labels=mood_labels,
        mood_values=mood_values,
        daily_labels=daily_labels,
        daily_values=daily_values
    )



    


