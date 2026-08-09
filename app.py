import os
from datetime import timedelta

import pymysql
from flask import Flask, request, jsonify, session, render_template
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.permanent_session_lifetime = timedelta(days=30)

# Render/production sits behind HTTPS - make cookies behave correctly there.
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)


def get_conn():
    """Open a fresh connection to the Aiven MySQL database.
    Credentials come ONLY from environment variables - never hard-coded."""
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ.get("MYSQL_PORT", 3306)),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        ssl={"ssl": {}},  # Aiven requires an encrypted connection
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_db():
    """Create the two tables we need if they don't exist yet. Safe to run every boot."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS app_state (
                    id INT PRIMARY KEY,
                    data LONGTEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )"""
            )
    finally:
        conn.close()


def require_login():
    return "username" in session


# ---------- Pages ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- Auth ----------
@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(force=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False}), 400

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cur.fetchone()
    finally:
        conn.close()

    if user and check_password_hash(user["password_hash"], password):
        session.permanent = True
        session["username"] = username
        return jsonify({"ok": True, "username": username})
    return jsonify({"ok": False}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session")
def get_session():
    if require_login():
        return jsonify({"logged_in": True, "username": session["username"]})
    return jsonify({"logged_in": False})


# ---------- Shared app data (one JSON blob, same as the browser-storage version used) ----------
@app.route("/api/state", methods=["GET"])
def get_state():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM app_state WHERE id=1")
            row = cur.fetchone()
    finally:
        conn.close()
    return jsonify({"data": row["data"] if row else None})


@app.route("/api/state", methods=["POST"])
def save_state():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True) or {}
    data = body.get("data", "")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_state (id, data) VALUES (1, %s)
                   ON DUPLICATE KEY UPDATE data=%s""",
                (data, data),
            )
    finally:
        conn.close()
    return jsonify({"ok": True})


# Create tables on startup (both local `python app.py` and Render/gunicorn boot)
init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
