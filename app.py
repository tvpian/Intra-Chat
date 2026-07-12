"""
Intra-Chat — a lightweight self-hosted LAN chat with file sharing, a tech
manual, a shared brain-dump board, real-time notifications, and an optional
local-LLM summariser.

Configuration comes entirely from environment variables (see `.env.example`).
"""

import csv
import datetime
import glob
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid

from flask import (
    Flask,
    g,
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
API_KEYS_FILE = os.path.join(HERE, "api_keys.json")
INVENTORY_FILE = os.path.join(HERE, "inventory.json")
MEMBERS_FILE = os.path.join(HERE, "members.json")
PROJECTS_FILE = os.path.join(HERE, "projects.json")
MAX_MESSAGES = 200
MESSAGE_EXPIRY_DAYS = 30
MAX_NOTIFICATIONS = 100

# ── Inventory config ─────────────────────────────────────────────────────────
# Lab equipment / asset tracking — each row is a distinct piece of equipment
# with a status and (optionally) whoever is currently in charge of it.
INVENTORY_CATEGORIES = [
    "sensors", "motors", "controllers", "cables", "tools", "robots",
    "electronics", "computers", "batteries", "misc",
]
# Short codes baked into printable asset tags so a label reads LAB138-SEN-0003
# (lab number + category + procurement order), making shelved gear identifiable
# at a glance and traceable to the lab it belongs to.
INVENTORY_CATEGORY_CODES = {
    "sensors": "SEN", "motors": "MOT", "controllers": "CTL", "cables": "CAB",
    "tools": "TOL", "robots": "ROB", "electronics": "ELE", "computers": "CMP",
    "batteries": "BAT", "misc": "MSC",
}
# Lab identifier that leads every asset tag (override with the LAB_NO env var).
LAB_NO = os.environ.get("LAB_NO", "138").strip() or "138"
ASSET_TAG_PREFIX = f"LAB{LAB_NO}"
INVENTORY_STATUSES = {"available", "in_use", "borrowed", "lost", "retired", "broken"}
# Statuses that mean somebody currently has the item, so an "in charge" person
# is expected / preserved. Other statuses clear it (or keep it for accountability).
INVENTORY_IN_USE_STATUSES = {"in_use", "borrowed"}


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


def _save_json_atomic(path, data):
    """Write JSON atomically (temp file + os.replace) and keep a .bak of the
    previous version. Used for files that agents/scripts write to frequently
    (api keys, braindump, inventory) to avoid the corruption seen in this
    repo's *.recovered files."""
    directory = os.path.dirname(path) or "."
    tmp_path = None
    try:
        if os.path.exists(path):
            shutil.copyfile(path, path + ".bak")
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except OSError as exc:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
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
    _save_json_atomic(BRAINDUMP_FILE, entries)


def load_notifications():
    return _load_json(NOTIFICATIONS_FILE, [])


def save_notifications(notifs):
    _save_json(NOTIFICATIONS_FILE, notifs)


def load_api_keys():
    return _load_json(API_KEYS_FILE, [])


def save_api_keys(keys):
    _save_json_atomic(API_KEYS_FILE, keys)


def load_inventory():
    return _load_json(INVENTORY_FILE, [])


def save_inventory(items):
    _save_json_atomic(INVENTORY_FILE, items)


def load_members():
    return _load_json(MEMBERS_FILE, [])


def save_members(members):
    _save_json_atomic(MEMBERS_FILE, members)


def load_projects():
    return _load_json(PROJECTS_FILE, [])


def save_projects(projects):
    _save_json_atomic(PROJECTS_FILE, projects)


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


# ── API keys (machine-to-machine auth for per-project agents) ───────────────
def _generate_api_key(project_id):
    slug = re.sub(r"[^a-z0-9]+", "-", project_id.lower()).strip("-") or "project"
    return f"ic_{slug}_{secrets.token_hex(16)}"


def _hash_api_key(raw_key):
    return hashlib.sha256(f"{raw_key}{SECRET_KEY}".encode("utf-8")).hexdigest()


def _valid_api_key():
    """Checks the Authorization: Bearer <key> header against api_keys.json.
    Returns the bound project_id on success, else None. Updates last_used_at
    on the matching key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    raw_key = auth[len("Bearer "):].strip()
    if not raw_key:
        return None
    hashed = _hash_api_key(raw_key)
    keys = load_api_keys()
    for rec in keys:
        if rec.get("key_hash") == hashed and not rec.get("revoked_at"):
            rec["last_used_at"] = datetime.datetime.now().isoformat()
            save_api_keys(keys)
            return rec.get("project_id")
    return None


@app.before_request
def _check_auth():
    if (
        request.endpoint in {"login", "login_post", "static"}
        or request.path.startswith("/socket.io/")
        or request.path.startswith("/static/")
        or request.path == "/favicon.ico"
    ):
        return
    is_kb_path = request.path.startswith("/api/braindump") or request.path.startswith("/api/inventory")
    if is_kb_path:
        # Resolve the API key first (independent of session state) so that a
        # logged-in browser that ALSO supplies its project's key gets
        # g.api_project_id set — needed for ownership checks on private
        # knowledge-base entries. Session auth alone must not short-circuit
        # this, or a teammate's browser could never "unlock" their project.
        project_id = _valid_api_key()
        if project_id:
            g.api_project_id = project_id
    if request.path.startswith("/api/") and session.get("authorized"):
        return
    if is_kb_path and getattr(g, "api_project_id", None):
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


# ── API keys (admin, browser/session only) ──────────────────────────────────
@app.route("/admin/api-keys")
def api_keys_page():
    return render_template("api_keys.html")


@app.route("/api/keys", methods=["GET"])
def api_keys_list():
    keys = load_api_keys()
    safe = [{k: v for k, v in rec.items() if k != "key_hash"} for rec in keys]
    return jsonify(safe)


@app.route("/api/keys", methods=["POST"])
def api_keys_create():
    data = request.get_json(force=True) or {}
    project_id = (data.get("project_id") or "").strip()
    label = (data.get("label") or "").strip()
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    raw_key = _generate_api_key(project_id)
    record = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "label": label or project_id,
        "key_hash": _hash_api_key(raw_key),
        "created_at": datetime.datetime.now().isoformat(),
        "last_used_at": None,
        "revoked_at": None,
    }
    keys = load_api_keys()
    keys.append(record)
    save_api_keys(keys)
    push_notification(
        "api_key",
        f"🔑 New API key created for {project_id}",
        label or project_id,
        link="/admin/api-keys",
    )
    response = {k: v for k, v in record.items() if k != "key_hash"}
    response["api_key"] = raw_key  # shown once; never persisted or returned again
    return jsonify(response), 201


@app.route("/api/keys/<key_id>/revoke", methods=["POST"])
def api_keys_revoke(key_id):
    keys = load_api_keys()
    for rec in keys:
        if rec["id"] == key_id:
            rec["revoked_at"] = datetime.datetime.now().isoformat()
            save_api_keys(keys)
            return jsonify({"status": "revoked"})
    return jsonify({"error": "Not found"}), 404


# ── Members & projects (teammate → projects → knowledge base) ───────────────
def _hash_passcode(raw):
    return hashlib.sha256(f"pc:{raw}{SECRET_KEY}".encode("utf-8")).hexdigest()


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "project"


def _current_member():
    mid = session.get("member_id")
    if not mid:
        return None
    return next((m for m in load_members() if m["id"] == mid), None)


def _member_name(member_id, members=None):
    members = members if members is not None else load_members()
    m = next((x for x in members if x["id"] == member_id), None)
    return m["name"] if m else "Unknown"


def _projects_by_id(projects=None):
    projects = projects if projects is not None else load_projects()
    return {p["id"]: p for p in projects}


def _member_owns_project(project_id, pmap=None):
    member = _current_member()
    if not member:
        return False
    pmap = pmap if pmap is not None else _projects_by_id()
    proj = pmap.get(project_id)
    return bool(proj and proj.get("owner") == member["id"])


@app.route("/workspace")
def workspace_page():
    return render_template("workspace.html")


@app.route("/api/member/me")
def api_member_me():
    m = _current_member()
    if not m:
        return jsonify({"member": None})
    return jsonify({"member": {"id": m["id"], "name": m["name"]}})


@app.route("/api/member/auth", methods=["POST"])
def api_member_auth():
    """Sign in an existing teammate (name + passcode) or create a new one.
    The passcode is this teammate's personal credential for owning/editing
    their private knowledge bases from the browser."""
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    passcode = (data.get("passcode") or "").strip()
    if not name or not passcode:
        return jsonify({"error": "Name and passcode are required"}), 400
    if len(passcode) < 4:
        return jsonify({"error": "Passcode must be at least 4 characters"}), 400

    members = load_members()
    existing = next((m for m in members if m["name"].lower() == name.lower()), None)
    if existing:
        if existing["passcode_hash"] != _hash_passcode(passcode):
            return jsonify({"error": "Wrong passcode for this name"}), 403
        member = existing
        created = False
    else:
        member = {
            "id": str(uuid.uuid4()),
            "name": name,
            "passcode_hash": _hash_passcode(passcode),
            "created_at": datetime.datetime.now().isoformat(),
        }
        members.append(member)
        save_members(members)
        created = True

    session["member_id"] = member["id"]
    return jsonify({
        "member": {"id": member["id"], "name": member["name"]},
        "created": created,
    })


@app.route("/api/member/logout", methods=["POST"])
def api_member_logout():
    session.pop("member_id", None)
    return jsonify({"status": "signed out"})


def _project_public_entry_count(project_id, entries=None):
    entries = entries if entries is not None else load_braindump()
    return sum(
        1 for e in entries
        if e.get("project_id") == project_id and e.get("visibility") == "team"
    )


@app.route("/api/projects", methods=["GET"])
def api_projects_list():
    member = _current_member()
    if not member:
        return jsonify({"error": "Sign in to your workspace first"}), 401
    entries = load_braindump()
    counts = {}
    for e in entries:
        pid = e.get("project_id", "general")
        counts[pid] = counts.get(pid, 0) + 1
    mine = [p for p in load_projects() if p.get("owner") == member["id"]]
    out = []
    for p in mine:
        out.append({
            "id": p["id"],
            "name": p.get("name", p["id"]),
            "public": bool(p.get("public")),
            "created_at": p.get("created_at"),
            "entry_count": counts.get(p["id"], 0),
            "public_entry_count": _project_public_entry_count(p["id"], entries),
        })
    out.sort(key=lambda x: x["name"].lower())
    return jsonify(out)


@app.route("/api/projects", methods=["POST"])
def api_projects_create():
    member = _current_member()
    if not member:
        return jsonify({"error": "Sign in to your workspace first"}), 401
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    projects = load_projects()
    base = _slugify(name)
    slug = base
    n = 2
    existing_ids = {p["id"] for p in projects}
    while slug in existing_ids or slug == "general":
        slug = f"{base}-{n}"
        n += 1
    proj = {
        "id": slug,
        "name": name,
        "owner": member["id"],
        "public": bool(data.get("public", True)),
        "created_at": datetime.datetime.now().isoformat(),
    }
    projects.append(proj)
    save_projects(projects)
    return jsonify({
        "id": proj["id"], "name": proj["name"], "public": proj["public"],
        "entry_count": 0, "public_entry_count": 0, "created_at": proj["created_at"],
    }), 201


@app.route("/api/projects/<project_id>", methods=["PUT"])
def api_projects_update(project_id):
    member = _current_member()
    if not member:
        return jsonify({"error": "Sign in to your workspace first"}), 401
    projects = load_projects()
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        return jsonify({"error": "Not found"}), 404
    if proj.get("owner") != member["id"]:
        return jsonify({"error": "You do not own this project"}), 403
    data = request.get_json(force=True) or {}
    if "name" in data and (data["name"] or "").strip():
        proj["name"] = data["name"].strip()
    if "public" in data:
        proj["public"] = bool(data["public"])
        # Toggling a project's public flag bulk-applies to all its notes, so
        # "share this project" / "make private" behaves the way people expect.
        entries = load_braindump()
        new_vis = "team" if proj["public"] else "private"
        changed = False
        for e in entries:
            if e.get("project_id") == project_id and e.get("visibility") != new_vis:
                e["visibility"] = new_vis
                e["updated_at"] = datetime.datetime.now().isoformat()
                changed = True
        if changed:
            save_braindump(entries)
    save_projects(projects)
    return jsonify({"id": proj["id"], "name": proj["name"], "public": proj["public"]})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_projects_delete(project_id):
    member = _current_member()
    if not member:
        return jsonify({"error": "Sign in to your workspace first"}), 401
    projects = load_projects()
    proj = next((p for p in projects if p["id"] == project_id), None)
    if not proj:
        return jsonify({"error": "Not found"}), 404
    if proj.get("owner") != member["id"]:
        return jsonify({"error": "You do not own this project"}), 403
    # Delete the project and its knowledge-base entries.
    entries = [e for e in load_braindump() if e.get("project_id") != project_id]
    save_braindump(entries)
    save_projects([p for p in projects if p["id"] != project_id])
    # Revoke any API keys bound to this project.
    keys = load_api_keys()
    changed = False
    for rec in keys:
        if rec.get("project_id") == project_id and not rec.get("revoked_at"):
            rec["revoked_at"] = datetime.datetime.now().isoformat()
            changed = True
    if changed:
        save_api_keys(keys)
    return jsonify({"status": "deleted"})


@app.route("/api/projects/<project_id>/api-key", methods=["POST"])
def api_projects_generate_key(project_id):
    """Generate an agent API key bound to a project the member owns. Used to
    connect a teammate's VS Code Copilot agent to this project's KB."""
    member = _current_member()
    if not member:
        return jsonify({"error": "Sign in to your workspace first"}), 401
    proj = _projects_by_id().get(project_id)
    if not proj:
        return jsonify({"error": "Not found"}), 404
    if proj.get("owner") != member["id"]:
        return jsonify({"error": "You do not own this project"}), 403
    raw_key = _generate_api_key(project_id)
    record = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "label": f"{proj.get('name', project_id)} ({member['name']})",
        "key_hash": _hash_api_key(raw_key),
        "created_at": datetime.datetime.now().isoformat(),
        "last_used_at": None,
        "revoked_at": None,
    }
    keys = load_api_keys()
    keys.append(record)
    save_api_keys(keys)
    return jsonify({"api_key": raw_key, "project_id": project_id}), 201


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


@app.route("/knowledge")
def knowledge_page():
    return redirect(url_for("workspace_page"))


def _entry_visibility(e):
    # Legacy/general-board entries (no owning project) have always been
    # fully open — keep them permanently "team" visible.
    if e.get("project_id", "general") == "general":
        return "team"
    return e.get("visibility", "private")


def _entry_is_public(e, pmap=None):
    """An entry appears on the shared team board when it is marked
    team-visible. Notes are public by default; a teammate can mark an
    individual note (or a whole project) private. Legacy 'general' entries
    are always public."""
    if e.get("project_id", "general") == "general":
        return True
    return e.get("visibility", "team") == "team"


def _can_manage_entry(e, pmap=None):
    """An entry may be edited/deleted by: anyone (legacy 'general' board),
    the owning project's API key (agents), or the signed-in teammate who
    owns the project (browser)."""
    project_id = e.get("project_id", "general")
    if project_id == "general":
        return True
    if getattr(g, "api_project_id", None) == project_id:
        return True
    return _member_owns_project(project_id, pmap)


def _enrich_entry(e, pmap, members):
    project_id = e.get("project_id", "general")
    proj = pmap.get(project_id)
    out = dict(e)
    out["project_name"] = proj.get("name", project_id) if proj else (
        "Team Board" if project_id == "general" else project_id
    )
    out["project_public"] = bool(proj.get("public")) if proj else (project_id == "general")
    out["owner_name"] = _member_name(proj["owner"], members) if proj and proj.get("owner") else None
    return out


@app.route("/api/braindump", methods=["GET"])
def api_braindump_list():
    entries = load_braindump()
    tag = request.args.get("tag", "").strip()
    author = request.args.get("author", "").strip()
    project_id = request.args.get("project_id", "").strip()
    mine_only = request.args.get("mine", "").strip() == "1"
    q = request.args.get("q", "").strip().lower()
    authed_project = getattr(g, "api_project_id", None)
    member = _current_member()
    pmap = _projects_by_id()
    members = load_members()

    if mine_only:
        # A teammate's private view: entries from projects they own (browser
        # session) or the single project their API key is bound to (agent).
        if member:
            owned = {p["id"] for p in pmap.values() if p.get("owner") == member["id"]}
            entries = [e for e in entries if e.get("project_id", "general") in owned]
        elif authed_project:
            entries = [e for e in entries if e.get("project_id", "general") == authed_project]
        else:
            return jsonify({"error": "Sign in to your workspace (or use a project API key) to view a private knowledge base"}), 401
    else:
        # Shared team board: only public projects' team-visible entries.
        entries = [e for e in entries if _entry_is_public(e, pmap)]

    if tag:
        entries = [e for e in entries if tag.lower() in [t.lower() for t in e.get("tags", [])]]
    if author:
        entries = [e for e in entries if e.get("author", "").lower() == author.lower()]
    if project_id:
        entries = [e for e in entries if e.get("project_id", "general") == project_id]
    if q:
        entries = [
            e for e in entries
            if q in e.get("title", "").lower() or q in e.get("content", "").lower()
        ]
    entries.sort(key=lambda x: x.get("pinned", False), reverse=True)
    return jsonify([_enrich_entry(e, pmap, members) for e in entries])


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

    authed_project = getattr(g, "api_project_id", None)
    # An agent authenticating with a project's API key defaults to dumping into
    # that project's knowledge base — it shouldn't have to repeat the project id.
    default_project = authed_project or "general"
    requested_project = (data.get("project_id") or default_project).strip() or default_project
    member = _current_member()

    if requested_project == "general":
        project_id = "general"
        visibility = "team"  # legacy shared board is always fully open
    else:
        # Posting into a project-owned knowledge base requires either that
        # project's own API key (agents) or being signed in as the teammate
        # who owns the project (browser). This is what makes private
        # knowledge bases actually private.
        owns = (authed_project == requested_project) or _member_owns_project(requested_project)
        if not owns:
            return jsonify({"error": "You must own this project (sign in) or use its API key to post to its knowledge base"}), 403
        project_id = requested_project
        # Notes are public by default; the author can explicitly mark private.
        visibility = data.get("visibility") if data.get("visibility") in ("private", "team") else "team"

    is_pure_agent = bool(authed_project) and not member and not session.get("authorized")
    source = "agent" if is_pure_agent else "human"
    if is_pure_agent:
        author = author or authed_project
    elif member and (not author or author == "Anonymous"):
        author = member["name"]

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
        "project_id": project_id,
        "source": source,
        "visibility": visibility,
        "created_at": now,
        "updated_at": now,
    }
    entries.insert(0, entry)
    save_braindump(entries)

    if visibility == "private":
        # Don't leak private content into the team-wide notification feed —
        # just announce that activity happened.
        notif_title = f"🔒 {'Agent' if source == 'agent' else author} added to {project_id}'s private knowledge base"
        notif_body = ""
    else:
        prefix = f"🤖 [{project_id}] agent dumped" if source == "agent" else f"🧠 {author} dumped"
        notif_title = f"{prefix}: {entry['title']}"
        notif_body = content[:120] + ("..." if len(content) > 120 else "")
    push_notification("braindump", notif_title, notif_body, author=author, link="/braindump")
    return jsonify(entry), 201


@app.route("/api/braindump/<entry_id>", methods=["PUT"])
def api_braindump_update(entry_id):
    data = request.get_json(force=True) or {}
    entries = load_braindump()
    for e in entries:
        if e["id"] != entry_id:
            continue

        # Reactions are the one exception: any teammate may react, even to
        # entries they don't own (matches prior open behavior).
        if set(data.keys()) - {"react"} and not _can_manage_entry(e):
            return jsonify({"error": "Only the project owner (or its API key) can edit this entry"}), 403

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
        if "visibility" in data and e.get("project_id", "general") != "general" and data["visibility"] in ("private", "team"):
            e["visibility"] = data["visibility"]
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
    entries = load_braindump()
    target = next((e for e in entries if e["id"] == entry_id), None)
    if target is None:
        return jsonify({"error": "Not found"}), 404
    if not _can_manage_entry(target):
        return jsonify({"error": "Only the project owner (or its API key) can delete this entry"}), 403
    entries = [e for e in entries if e["id"] != entry_id]
    save_braindump(entries)
    return jsonify({"status": "deleted"})


@app.route("/api/braindump/export")
def api_braindump_export():
    authed_project = getattr(g, "api_project_id", None)
    member = _current_member()
    pmap = _projects_by_id()
    owned = set()
    if member:
        owned = {p["id"] for p in pmap.values() if p.get("owner") == member["id"]}
    if authed_project:
        owned.add(authed_project)
    entries = [
        e for e in load_braindump()
        if _entry_is_public(e, pmap) or e.get("project_id", "general") in owned
    ]
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


# ── Inventory ────────────────────────────────────────────────────────────────
@app.route("/inventory")
def inventory_page():
    return render_template(
        "inventory.html",
        categories=INVENTORY_CATEGORIES,
        category_codes=INVENTORY_CATEGORY_CODES,
        asset_tag_prefix=ASSET_TAG_PREFIX,
    )


@app.route("/api/inventory/categories")
def api_inventory_categories():
    return jsonify(INVENTORY_CATEGORIES)


@app.route("/api/inventory", methods=["GET"])
def api_inventory_list():
    items = load_inventory()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()
    location = request.args.get("location", "").strip().lower()
    q = request.args.get("q", "").strip().lower()
    if category:
        items = [i for i in items if i.get("category") == category]
    if status:
        items = [i for i in items if i.get("status") == status]
    if location:
        items = [i for i in items if location in (i.get("location", "").lower())]
    if q:
        def _match(i):
            hay = " ".join([
                i.get("name", ""), i.get("asset_tag", ""), i.get("manufacturer", ""),
                i.get("model_number", ""), i.get("serial_number", ""),
                i.get("location", ""), i.get("in_charge", "") or i.get("holder", ""), i.get("notes", ""),
                " ".join(i.get("tags", []) if isinstance(i.get("tags"), list) else []),
            ]).lower()
            return q in hay
        items = [i for i in items if _match(i)]
    items.sort(key=lambda x: x.get("name", "").lower())
    return jsonify(items)


def _inventory_summary(items):
    counts = {s: 0 for s in INVENTORY_STATUSES}
    for i in items:
        st = i.get("status", "available")
        counts[st] = counts.get(st, 0) + 1
    return {"total": len(items), "by_status": counts}


@app.route("/api/inventory/summary")
def api_inventory_summary():
    return jsonify(_inventory_summary(load_inventory()))


def _category_code(category):
    return INVENTORY_CATEGORY_CODES.get(category, "MSC")


def _next_asset_tag(items, category):
    """Generate a printable asset tag like LAB138-SEN-0003 that encodes the lab
    number, category, and per-category procurement order, ready for a label maker."""
    code = _category_code(category)
    prefix = f"{ASSET_TAG_PREFIX}-{code}-"
    n = 0
    for i in items:
        tag = i.get("asset_tag", "") or ""
        if tag.startswith(prefix):
            m = re.search(r"(\d+)\s*$", tag)
            if m:
                n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:04d}"


def _team_roster():
    """Names that can be assigned as 'in charge' — signed-in teammates, any
    extra names from the TEAM_ROSTER env var, plus whoever already appears on
    existing inventory. Free-text is still allowed client-side (datalist)."""
    names = []
    seen = set()

    def add(raw):
        n = (raw or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)

    for m in load_members():
        add(m.get("name"))
    for extra in os.environ.get("TEAM_ROSTER", "").split(","):
        add(extra)
    for i in load_inventory():
        add(i.get("in_charge") or i.get("holder"))
    names.sort(key=str.lower)
    return names


@app.route("/api/inventory/roster")
def api_inventory_roster():
    return jsonify(_team_roster())


@app.route("/api/inventory", methods=["POST"])
def api_inventory_create():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    category = data.get("category") or "misc"
    if category not in INVENTORY_CATEGORIES:
        category = "misc"

    status = data.get("status") if data.get("status") in INVENTORY_STATUSES else "available"
    in_charge = (data.get("in_charge") or data.get("holder") or "").strip()
    # "In charge" only sticks while the item is actually out with someone.
    if status not in INVENTORY_IN_USE_STATUSES:
        in_charge = ""

    items = load_inventory()
    asset_tag = (data.get("asset_tag") or "").strip() or _next_asset_tag(items, category)
    user = (data.get("user") or in_charge or "").strip()
    now = datetime.datetime.now().isoformat()
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    item = {
        "id": str(uuid.uuid4()),
        "asset_tag": asset_tag,
        "name": name,
        "category": category,
        "manufacturer": (data.get("manufacturer") or "").strip(),
        "model_number": (data.get("model_number") or "").strip(),
        "serial_number": (data.get("serial_number") or "").strip(),
        "location": (data.get("location") or "").strip(),
        "status": status,
        "in_charge": in_charge,
        "notes": (data.get("notes") or "").strip(),
        "tags": tags,
        "created_at": now,
        "updated_at": now,
        "history": [{"action": "created", "user": user or "Unknown", "detail": f"status={status}", "timestamp": now}],
    }
    items.append(item)
    save_inventory(items)
    push_notification(
        "inventory",
        f"📦 New equipment: {item['name']}",
        f"{asset_tag} · {category}",
        author=user or "System",
        link="/inventory",
    )
    return jsonify(item), 201


@app.route("/api/inventory/<item_id>", methods=["PUT"])
def api_inventory_update(item_id):
    data = request.get_json(force=True) or {}
    items = load_inventory()
    for item in items:
        if item["id"] != item_id:
            continue
        for field in ("name", "manufacturer", "model_number", "serial_number", "location", "notes", "asset_tag"):
            if field in data:
                item[field] = (data[field] or "").strip()
        if "category" in data and data["category"] in INVENTORY_CATEGORIES:
            item["category"] = data["category"]
        if "tags" in data:
            tags = data["tags"]
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            item["tags"] = tags
        if "status" in data and data["status"] in INVENTORY_STATUSES:
            old_status = item.get("status")
            item["status"] = data["status"]
            # Returning to the shelf clears whoever was in charge.
            if item["status"] == "available":
                item["in_charge"] = ""
            if item["status"] != old_status:
                user = (data.get("user") or "").strip()
                item.setdefault("history", []).append({
                    "action": "status_change",
                    "user": user or "Unknown",
                    "detail": f"{old_status} → {item['status']}",
                    "timestamp": datetime.datetime.now().isoformat(),
                })
        if "in_charge" in data or "holder" in data:
            item["in_charge"] = (data.get("in_charge") or data.get("holder") or "").strip()
        item["updated_at"] = datetime.datetime.now().isoformat()
        save_inventory(items)
        return jsonify(item)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/inventory/<item_id>", methods=["DELETE"])
def api_inventory_delete(item_id):
    items = [i for i in load_inventory() if i["id"] != item_id]
    save_inventory(items)
    return jsonify({"status": "deleted"})


@app.route("/api/inventory/<item_id>/checkout", methods=["POST"])
def api_inventory_checkout(item_id):
    data = request.get_json(force=True) or {}
    in_charge = (data.get("in_charge") or data.get("holder") or data.get("user") or "").strip()
    if not in_charge:
        return jsonify({"error": "Who's taking it? Please pick who's in charge."}), 400
    # In use (kept in the lab) vs borrowed (taken away) — default to in_use.
    new_status = data.get("status") if data.get("status") in INVENTORY_IN_USE_STATUSES else "in_use"
    items = load_inventory()
    for item in items:
        if item["id"] != item_id:
            continue
        if item.get("status") in INVENTORY_IN_USE_STATUSES:
            holder = item.get("in_charge") or item.get("holder") or "someone"
            return jsonify({"error": f"Already {item['status'].replace('_', ' ')} by {holder}."}), 409
        if item.get("status") in ("retired", "lost", "broken"):
            return jsonify({"error": f"This item is {item['status']} and can't be taken out."}), 409
        now = datetime.datetime.now().isoformat()
        item["status"] = new_status
        item["in_charge"] = in_charge
        item["updated_at"] = now
        item.setdefault("history", []).append({
            "action": new_status, "user": in_charge, "detail": data.get("notes", ""), "timestamp": now,
        })
        save_inventory(items)
        verb = "is using" if new_status == "in_use" else "borrowed"
        push_notification(
            "inventory",
            f"📤 {in_charge} {verb} {item['name']}",
            f"{item.get('asset_tag', '')}",
            author=in_charge,
            link="/inventory",
        )
        return jsonify(item)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/inventory/<item_id>/checkin", methods=["POST"])
def api_inventory_checkin(item_id):
    data = request.get_json(force=True) or {}
    user = (data.get("user") or "").strip()
    items = load_inventory()
    for item in items:
        if item["id"] != item_id:
            continue
        prev_holder = item.get("in_charge") or item.get("holder", "")
        now = datetime.datetime.now().isoformat()
        item["status"] = "available"
        item["in_charge"] = ""
        if (data.get("location") or "").strip():
            item["location"] = data["location"].strip()
        item["updated_at"] = now
        item.setdefault("history", []).append({
            "action": "returned", "user": user or prev_holder or "Unknown",
            "detail": data.get("notes", ""), "timestamp": now,
        })
        save_inventory(items)
        push_notification(
            "inventory",
            f"📥 {item['name']} returned",
            f"{item.get('asset_tag', '')} · back in the lab",
            author=user or prev_holder or "System",
            link="/inventory",
        )
        return jsonify(item)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/inventory/export")
def api_inventory_export():
    fmt = request.args.get("format", "md").strip().lower()
    items = load_inventory()
    items.sort(key=lambda x: (x.get("category", ""), x.get("name", "").lower()))
    if fmt == "csv":
        cols = ["asset_tag", "name", "category", "manufacturer", "model_number",
                "serial_number", "location", "status", "in_charge", "notes"]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(cols)
        for i in items:
            row = []
            for c in cols:
                if c == "in_charge":
                    row.append(i.get("in_charge", "") or i.get("holder", ""))
                else:
                    row.append(i.get(c, ""))
            writer.writerow(row)
        return out.getvalue(), 200, {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=inventory.csv",
        }
    lines = ["# Lab Equipment Inventory", ""]
    summary = _inventory_summary(items)
    lines.append(f"_Total assets: {summary['total']}_")
    lines.append("")
    for i in items:
        lines.append(f"## {i.get('name', 'Unnamed')}  ")
        if i.get("asset_tag"):
            lines.append(f"**Asset Tag:** {i['asset_tag']}  ")
        lines.append(f"**Category:** {i.get('category', 'misc')}  ")
        lines.append(f"**Status:** {i.get('status', 'available')}  ")
        in_charge = i.get("in_charge", "") or i.get("holder", "")
        if in_charge:
            lines.append(f"**In charge:** {in_charge}  ")
        for label, key in (("Manufacturer", "manufacturer"), ("Model", "model_number"),
                           ("Serial", "serial_number"), ("Location", "location")):
            if i.get(key):
                lines.append(f"**{label}:** {i[key]}  ")
        if i.get("tags"):
            lines.append(f"**Tags:** {', '.join(i['tags'])}  ")
        if i.get("notes"):
            lines.append("")
            lines.append(i["notes"])
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
