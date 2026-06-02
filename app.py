"""
Intra-Chat — a lightweight self-hosted LAN chat with file sharing, a tech
manual, a shared brain-dump board, real-time notifications, and an optional
local-LLM summariser.

Configuration comes entirely from environment variables (see `.env.example`).
"""

import datetime
import glob
import json
import os
import re
import secrets
import time
import uuid

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS
from flask_socketio import SocketIO, send
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

from ai_engine import summarize_text


# ── Configuration ────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5656"))
DEBUG_LOGS = os.environ.get("DEBUG_LOGS", "0") == "1"

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))
LOCK_MS = int(os.environ.get("LOCK_MS", "30000"))

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or os.path.join(HERE, "uploads")
TEAM_DOCS_PATH = os.environ.get("TEAM_DOCS_PATH", "").strip() or None

CHAT_HISTORY_FILE = os.path.join(HERE, "chat_history.json")
TECH_MANUAL_FILE = os.path.join(HERE, "tech_manual.json")
BRAINDUMP_FILE = os.path.join(HERE, "braindump.json")
NOTIFICATIONS_FILE = os.path.join(HERE, "notifications.json")
MAX_MESSAGES = 200
MESSAGE_EXPIRY_DAYS = 30
MAX_NOTIFICATIONS = 100


# ── Upload categories ────────────────────────────────────────────────────────
UPLOAD_CATEGORIES = {
    "images":      {"extensions": {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "svg", "webp"}},
    "documents":   {"extensions": {"txt", "pdf", "zip", "docx", "xlsx", "md", "rtf", "odt", "ods"}},
    "code":        {"extensions": {"py", "js", "css", "html", "json", "cpp", "c", "h", "hpp", "java", "php", "rb", "go", "rs", "ts", "jsx", "tsx", "vue", "sh", "bat", "ps1"}},
    "robotics":    {"extensions": {"urdf", "stl", "step", "iges", "usd", "obj", "dae", "mesh", "sdf", "xacro"}},
    "configs":     {"extensions": {"cfg", "yaml", "yml", "xml", "conf", "ini", "toml", "env", "properties"}},
    "models":      {"extensions": {"pt", "pth", "onnx", "h5", "ckpt", "pkl", "joblib", "model", "weights", "pb"}},
    "videos":      {"extensions": {"mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v", "3gp"}},
    "audio":       {"extensions": {"mp3", "wav", "ogg", "flac", "aac", "m4a", "wma", "opus"}},
    "media":       {"extensions": {"psd", "ai", "eps", "indd", "sketch", "fig", "blend", "max", "3ds", "fbx", "dxf", "dwg"}},
    "docker":      {"extensions": {"dockerfile", "dockerignore", "docker-compose"}},
    "debs":        {"extensions": {"deb", "rpm", "pkg", "dmg", "msi", "exe", "appimage", "snap", "flatpak"}},
    "scripts":     {"extensions": {"bash", "zsh", "fish", "csh", "tcsh", "ksh", "pwsh", "cmd"}},
    "test_samples":{"extensions": {"test", "sample", "example", "demo", "spec", "fixture"}},
    "misc":        {"extensions": set()},
}
for _name, _info in UPLOAD_CATEGORIES.items():
    _info["folder"] = os.path.join(UPLOAD_FOLDER, _name)

ALLOWED_EXTENSIONS = set()
for _info in UPLOAD_CATEGORIES.values():
    ALLOWED_EXTENSIONS.update(_info["extensions"])


# ── Bootstrap folders ────────────────────────────────────────────────────────
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
for _info in UPLOAD_CATEGORIES.values():
    os.makedirs(_info["folder"], exist_ok=True)


def _debug_log(filename: str, message: str) -> None:
    if not DEBUG_LOGS:
        return
    try:
        with open(os.path.join(HERE, filename), "a") as f:
            f.write(f"{datetime.datetime.utcnow().isoformat()}: {message}\n")
    except OSError:
        pass


# ── Persistence helpers ──────────────────────────────────────────────────────
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        _debug_log("upload_debug.log", f"save error {path}: {exc}")


def load_chat_history():
    data = _load_json(CHAT_HISTORY_FILE, [])
    now = datetime.datetime.utcnow()
    return [
        e for e in data
        if (now - datetime.datetime.fromisoformat(e["timestamp"])).days < MESSAGE_EXPIRY_DAYS
    ]


def save_chat_history(history):
    _save_json(CHAT_HISTORY_FILE, history)


def load_tech_manual():
    return _load_json(TECH_MANUAL_FILE, [])


def save_tech_manual(data):
    _save_json(TECH_MANUAL_FILE, data)


def load_braindump():
    return _load_json(BRAINDUMP_FILE, [])


def save_braindump(entries):
    _save_json(BRAINDUMP_FILE, entries)


def load_notifications():
    return _load_json(NOTIFICATIONS_FILE, [])


def save_notifications(notifs):
    _save_json(NOTIFICATIONS_FILE, notifs)


# ── Team docs (optional) ─────────────────────────────────────────────────────
def scan_team_documentation():
    if not TEAM_DOCS_PATH or not os.path.isdir(TEAM_DOCS_PATH):
        return []

    docs = []
    for file_path in glob.glob(os.path.join(TEAM_DOCS_PATH, "*.md")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = (
                title_match.group(1)
                if title_match
                else os.path.basename(file_path).replace(".md", "").replace("_", " ").title()
            )

            desc_match = re.search(r"^#.*?\n\n(.+?)(?:\n\n|\n#|$)", content, re.MULTILINE | re.DOTALL)
            description = (
                desc_match.group(1).strip()[:200] + "..."
                if desc_match
                else "Team documentation file"
            )

            stat = os.stat(file_path)
            docs.append({
                "title": title,
                "description": description,
                "file_path": file_path,
                "filename": os.path.basename(file_path),
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size": stat.st_size,
            })
        except OSError as exc:
            _debug_log("upload_debug.log", f"scan error {file_path}: {exc}")
    return docs


def get_team_doc_content(filename):
    if not TEAM_DOCS_PATH:
        return None
    file_path = os.path.realpath(os.path.join(TEAM_DOCS_PATH, filename))
    if not file_path.startswith(os.path.realpath(TEAM_DOCS_PATH) + os.sep):
        return None
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


# ── App / sockets ────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

allowed_ips = set()
chat_history = load_chat_history()


# ── Auth ─────────────────────────────────────────────────────────────────────
QUOTES = [
    "Code is poetry written in logic.",
    "Debugging is twice as hard as writing the code in the first place.",
    "The best error message is the one that never shows up.",
    "Talk is cheap. Show me the code.",
    "First, solve the problem. Then, write the code.",
    "Code never lies, comments sometimes do.",
    "Programming isn't about what you know; it's about what you can figure out.",
    "The most important property of a program is whether it accomplishes the intention of its user.",
]


def _client_ip():
    ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr) or ""
    ip = ip.split(",")[0].strip().replace("::ffff:", "")
    return ip


def _require_auth():
    if _client_ip() in allowed_ips or session.get("authorized"):
        return None
    return redirect(url_for("login"))


@app.before_request
def _check_auth():
    if (
        request.endpoint in {"login", "login_post", "static"}
        or request.path.startswith("/socket.io/")
        or request.path.startswith("/static/")
        or request.path == "/favicon.ico"
    ):
        return
    if request.path.startswith("/api/") and session.get("authorized"):
        return
    blocked = _require_auth()
    if blocked:
        return blocked


@app.route("/login")
def login():
    if not APP_PASSWORD:
        return (
            "<h1>Intra-Chat is not configured</h1>"
            "<p>Set <code>APP_PASSWORD</code> in your .env file. "
            "Run <code>python setup_password.py</code> for an interactive setup.</p>",
            500,
        )

    q = QUOTES[int(time.time()) % len(QUOTES)]
    err_type = request.args.get("err")
    left = int(request.args.get("left", 0))
    ms_remaining = int(request.args.get("ms", 0))

    err_html = ""
    if err_type == "bad":
        suffix = f" — {left} attempt{'s' if left != 1 else ''} left" if left else ""
        err_html = f'<div class="err">Incorrect password{suffix}.</div>'
    elif err_type == "locked":
        err_html = f'<div class="err">Too many attempts. Try again in {ms_remaining // 1000}s.</div>'

    return render_template("login.html", quote=q, err_html=err_html)


@app.route("/login", methods=["POST"])
def login_post():
    now = int(time.time() * 1000)
    if "login" not in session:
        session["login"] = {"attempts": 0, "lockedUntil": 0}

    if session["login"].get("lockedUntil", 0) > now:
        ms = session["login"]["lockedUntil"] - now
        return redirect(url_for("login", err="locked", ms=ms))

    password = (request.form.get("password") or "").strip()
    if password == APP_PASSWORD:
        session["login"] = {"attempts": 0, "lockedUntil": 0}
        allowed_ips.add(_client_ip())
        session["authorized"] = True
        return redirect(url_for("index"))

    session["login"]["attempts"] = session["login"].get("attempts", 0) + 1
    if session["login"]["attempts"] >= MAX_ATTEMPTS:
        session["login"]["lockedUntil"] = now + LOCK_MS
        return redirect(url_for("login", err="locked", ms=LOCK_MS))

    time.sleep(min(0.2 * session["login"]["attempts"], 1.5))
    left = MAX_ATTEMPTS - session["login"]["attempts"]
    return redirect(url_for("login", err="bad", left=left))


@app.route("/logout")
def logout():
    allowed_ips.discard(_client_ip())
    session.clear()
    return redirect(url_for("login"))


# ── File uploads ─────────────────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_category(filename):
    if "." not in filename:
        return "misc"
    ext = filename.rsplit(".", 1)[1].lower()
    for cat, info in UPLOAD_CATEGORIES.items():
        if ext in info["extensions"]:
            return cat
    return "misc"


def get_upload_folder_for_category(category):
    return UPLOAD_CATEGORIES.get(category, UPLOAD_CATEGORIES["misc"])["folder"]


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "" or not allowed_file(f.filename):
        return jsonify({"error": "Invalid filename"}), 400

    category = get_file_category(f.filename)
    folder = get_upload_folder_for_category(category)
    os.makedirs(folder, exist_ok=True)

    name = secure_filename(f"{datetime.datetime.utcnow().timestamp()}_{f.filename}")
    save_path = os.path.join(folder, name)
    f.save(save_path)

    _debug_log("upload_debug.log", f"UPLOAD {f.filename} -> {save_path} ({category})")
    return jsonify({
        "url": url_for("uploaded_file", category=category, filename=name),
        "name": f.filename,
        "category": category,
        "saved_as": name,
    })


@app.route("/uploads/<category>/<filename>")
def uploaded_file(category, filename):
    return send_from_directory(get_upload_folder_for_category(category), filename)


@app.route("/uploads/<filename>")
def uploaded_file_legacy(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/upload-categories")
def get_upload_categories():
    return jsonify({
        cat: {"extensions": list(info["extensions"]), "folder_path": info["folder"]}
        for cat, info in UPLOAD_CATEGORIES.items()
    })


# ── Chat ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/history")
def history():
    global chat_history
    chat_history = load_chat_history()
    return render_template("history.html", chat_history=chat_history)


@socketio.on("connect")
def handle_connect():
    send(json.dumps(chat_history), broadcast=False)


@socketio.on("message")
def handle_message(msg):
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "msg": msg}
    chat_history.append(entry)
    if len(chat_history) > MAX_MESSAGES:
        chat_history[:] = chat_history[-MAX_MESSAGES:]
    save_chat_history(chat_history)
    send(json.dumps(entry), broadcast=True)


@socketio.on("alert")
def handle_alert(alert_msg):
    send(json.dumps({"msg": "ALERT: " + alert_msg, "alert": True}), broadcast=True)


# ── Tech manual ──────────────────────────────────────────────────────────────
@app.route("/manual")
def manual():
    tech_manual = load_tech_manual()
    team_docs = scan_team_documentation()

    for doc in team_docs:
        tech_manual.append({
            "message": f"📋 **{doc['title']}**\n\n{doc['description']}\n\n*Team Documentation - {doc['filename']}*",
            "category": "Team Docs",
            "username": "System",
            "timestamp": doc["modified"],
            "is_team_doc": True,
            "filename": doc["filename"],
            "file_path": doc["file_path"],
        })

    q = request.args.get("q", "").strip().lower()
    if q:
        tech_manual = [
            e for e in tech_manual
            if q in e.get("message", "").lower()
            or q in e.get("category", "").lower()
            or q in e.get("username", "").lower()
        ]

    return render_template(
        "manual.html",
        entries=tech_manual,
        query=q,
        team_docs_count=len(team_docs),
    )


@app.route("/export", methods=["POST"])
def export_message():
    payload = request.get_json() or {}
    payload.setdefault("timestamp", datetime.datetime.utcnow().isoformat())
    tech_manual = load_tech_manual()
    tech_manual.append(payload)
    save_tech_manual(tech_manual)
    return jsonify({"status": "ok", "message": "Message exported to Tech Manual."})


# ── Team docs ────────────────────────────────────────────────────────────────
@app.route("/docs")
def docs_browser():
    return render_template("docs.html", docs=scan_team_documentation())


@app.route("/api/team-docs")
def api_team_docs():
    docs = scan_team_documentation()
    return jsonify({"success": True, "docs": docs, "count": len(docs)})


@app.route("/api/team-docs/<filename>")
def api_team_doc(filename):
    content = get_team_doc_content(filename)
    if content is None:
        return jsonify({"success": False, "error": "Document not found"}), 404
    return jsonify({"success": True, "filename": filename, "content": content})


# ── Summarize ────────────────────────────────────────────────────────────────
@app.route("/summarize", methods=["POST"])
def summarize_endpoint():
    data = request.get_json() or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    return jsonify({"summary": summarize_text(text, max_length=150, min_length=40)})


# ── Notifications ────────────────────────────────────────────────────────────
def push_notification(ntype, title, body, author="System", link=""):
    notifs = load_notifications()
    notif = {
        "id": str(uuid.uuid4()),
        "type": ntype,
        "title": title,
        "body": body,
        "author": author,
        "link": link,
        "created_at": datetime.datetime.now().isoformat(),
    }
    notifs.insert(0, notif)
    if len(notifs) > MAX_NOTIFICATIONS:
        notifs = notifs[:MAX_NOTIFICATIONS]
    save_notifications(notifs)
    socketio.emit("notification", notif)
    return notif


@app.route("/api/notifications")
def api_notifications_list():
    return jsonify(load_notifications()[:50])


@app.route("/api/notifications/clear", methods=["POST"])
def api_notifications_clear():
    save_notifications([])
    return jsonify({"status": "cleared"})


# ── Brain dump ───────────────────────────────────────────────────────────────
@app.route("/braindump")
def braindump_page():
    return render_template("braindump.html")


@app.route("/api/braindump", methods=["GET"])
def api_braindump_list():
    entries = load_braindump()
    tag = request.args.get("tag", "").strip()
    author = request.args.get("author", "").strip()
    q = request.args.get("q", "").strip().lower()
    if tag:
        entries = [e for e in entries if tag.lower() in [t.lower() for t in e.get("tags", [])]]
    if author:
        entries = [e for e in entries if e.get("author", "").lower() == author.lower()]
    if q:
        entries = [
            e for e in entries
            if q in e.get("title", "").lower() or q in e.get("content", "").lower()
        ]
    entries.sort(key=lambda x: x.get("pinned", False), reverse=True)
    return jsonify(entries)


@app.route("/api/braindump", methods=["POST"])
def api_braindump_create():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    author = (data.get("author") or "Anonymous").strip()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
    if not content:
        return jsonify({"error": "Content is required"}), 400

    entries = load_braindump()
    now = datetime.datetime.now().isoformat()
    entry = {
        "id": str(uuid.uuid4()),
        "title": title or "Untitled",
        "content": content,
        "author": author,
        "tags": tags,
        "reactions": {},
        "pinned": False,
        "created_at": now,
        "updated_at": now,
    }
    entries.insert(0, entry)
    save_braindump(entries)
    push_notification(
        "braindump",
        f"🧠 {author} dumped: {entry['title']}",
        content[:120] + ("..." if len(content) > 120 else ""),
        author=author,
        link="/braindump",
    )
    return jsonify(entry), 201


@app.route("/api/braindump/<entry_id>", methods=["PUT"])
def api_braindump_update(entry_id):
    data = request.get_json(force=True) or {}
    entries = load_braindump()
    for e in entries:
        if e["id"] != entry_id:
            continue
        if "title" in data:
            e["title"] = (data["title"] or "").strip()
        if "content" in data:
            e["content"] = (data["content"] or "").strip()
        if "tags" in data:
            tags = data["tags"]
            if isinstance(tags, str):
                tags = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
            e["tags"] = tags
        if "pinned" in data:
            e["pinned"] = bool(data["pinned"])
        if "react" in data:
            reactions = e.get("reactions", {})
            emoji = data["react"].get("emoji", "")
            user = data["react"].get("user", "Anonymous")
            if emoji:
                voters = reactions.get(emoji, [])
                if user in voters:
                    voters.remove(user)
                else:
                    voters.append(user)
                reactions[emoji] = voters
                e["reactions"] = reactions
        e["updated_at"] = datetime.datetime.now().isoformat()
        save_braindump(entries)
        return jsonify(e)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/braindump/<entry_id>", methods=["DELETE"])
def api_braindump_delete(entry_id):
    entries = [e for e in load_braindump() if e["id"] != entry_id]
    save_braindump(entries)
    return jsonify({"status": "deleted"})


@app.route("/api/braindump/export")
def api_braindump_export():
    entries = load_braindump()
    entries.sort(key=lambda x: x.get("pinned", False), reverse=True)
    lines = ["# Brain Dump Export", ""]
    for e in entries:
        prefix = "📌 " if e.get("pinned") else ""
        lines.append(f"## {prefix}{e.get('title', 'Untitled')}")
        lines.append(f"**Author:** {e.get('author', 'Anonymous')}  ")
        created = e.get("created_at", "")[:16].replace("T", " ")
        lines.append(f"**Date:** {created}  ")
        tags = e.get("tags", [])
        if tags:
            lines.append(f"**Tags:** {', '.join('#' + t for t in tags)}  ")
        lines.append("")
        lines.append(e.get("content", ""))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}


# ── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Intra-Chat starting on http://{HOST}:{PORT}")
    if not APP_PASSWORD:
        print("⚠️  APP_PASSWORD is not set. Run `python setup_password.py` first.")
    socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)
