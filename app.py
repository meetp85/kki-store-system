import os
import json
import base64
from datetime import timedelta

import pymysql
from flask import Flask, request, jsonify, session, render_template, Response
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.permanent_session_lifetime = timedelta(days=30)

# Render/production sits behind HTTPS - make cookies behave correctly there.
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@example.com")


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
    """Create the tables we need if they don't exist yet. Safe to run every boot."""
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
            cur.execute(
                """CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    endpoint VARCHAR(600) UNIQUE NOT NULL,
                    p256dh VARCHAR(255) NOT NULL,
                    auth VARCHAR(255) NOT NULL,
                    username VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255),
                    mimetype VARCHAR(100),
                    data LONGTEXT,
                    uploaded_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


# ---------- File uploads (Quality drawings, etc.) ----------
MAX_FILE_B64_CHARS = 12_000_000  # roughly ~9MB of actual file data


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True) or {}
    filename = (body.get("filename") or "file")[:255]
    mimetype = (body.get("mimetype") or "application/octet-stream")[:100]
    data = body.get("data", "")
    if not data:
        return jsonify({"ok": False, "error": "no file data"}), 400
    if len(data) > MAX_FILE_B64_CHARS:
        return jsonify({"ok": False, "error": "file too large (max ~9MB)"}), 400

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO files (filename, mimetype, data, uploaded_by) VALUES (%s,%s,%s,%s)",
                (filename, mimetype, data, session.get("username")),
            )
            file_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"ok": True, "id": file_id})


@app.route("/api/file/<int:file_id>")
def get_file(file_id):
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM files WHERE id=%s", (file_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    raw = base64.b64decode(row["data"])
    return Response(
        raw,
        mimetype=row["mimetype"],
        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'},
    )


# ---------- Push notifications ----------
@app.route("/api/push/vapid-public-key")
def push_public_key():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"key": VAPID_PUBLIC_KEY})


@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True) or {}
    endpoint = body.get("endpoint", "")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        return jsonify({"ok": False, "error": "incomplete subscription"}), 400
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO push_subscriptions (endpoint, p256dh, auth, username) VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE p256dh=%s, auth=%s, username=%s""",
                (endpoint, p256dh, auth, session.get("username"), p256dh, auth, session.get("username")),
            )
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True) or {}
    endpoint = body.get("endpoint", "")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM push_subscriptions WHERE endpoint=%s", (endpoint,))
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/push/send", methods=["POST"])
def push_send():
    """Broadcasts a notification to every subscribed device. Called by the
    frontend right after any stock-affecting action (Inward, Issue, Outward,
    Scrap, Tag change, Sales Order, Returnable Challan)."""
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    if not VAPID_PRIVATE_KEY:
        return jsonify({"ok": False, "error": "push not configured on server"}), 200

    body = request.get_json(force=True) or {}
    title = body.get("title", "KKI Stores")
    message = body.get("body", "")

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return jsonify({"ok": False, "error": "pywebpush not installed"}), 200

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM push_subscriptions")
            subs = cur.fetchall()

        sent, expired = 0, []
        for sub in subs:
            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=json.dumps({"title": title, "body": message}),
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_CLAIM_EMAIL},
                )
                sent += 1
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):
                    expired.append(sub["endpoint"])

        if expired:
            with conn.cursor() as cur:
                cur.executemany("DELETE FROM push_subscriptions WHERE endpoint=%s", [(e,) for e in expired])
    finally:
        conn.close()

    return jsonify({"ok": True, "sent": sent})


# Create tables on startup (both local `python app.py` and Render/gunicorn boot)
init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)

