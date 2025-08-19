from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, send
from flask_cors import CORS
import json
import os
import datetime
import secrets
from ai_engine import summarize_text  # Import the summarization function
from werkzeug.utils import secure_filename
from flask import send_from_directory
import glob
import re
import time

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv('/media/mbwh/pop/tvp_ws/local_chat_app/.env')  # Use absolute path
except ImportError:
    print("python-dotenv not installed. Using environment variables only.")
    print("Run: pip install python-dotenv")

# just after your existing imports:
# Try to use the team workspace common folder, fallback to local uploads
PREFERRED_UPLOAD_FOLDER = '/media/mbwh/pop/team_ws/common'
LOCAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

# Check if the preferred folder is accessible
try:
    os.makedirs(PREFERRED_UPLOAD_FOLDER, exist_ok=True)
    # Test write access
    test_file = os.path.join(PREFERRED_UPLOAD_FOLDER, '.write_test')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    BASE_UPLOAD_FOLDER = PREFERRED_UPLOAD_FOLDER
    
    # Log success to a file
    with open('upload_debug.log', 'a') as log:
        log.write(f"{datetime.datetime.now()}: SUCCESS - Using team workspace: {BASE_UPLOAD_FOLDER}\n")
        
except (OSError, PermissionError) as e:
    BASE_UPLOAD_FOLDER = LOCAL_UPLOAD_FOLDER
    
    # Log error to a file
    with open('upload_debug.log', 'a') as log:
        log.write(f"{datetime.datetime.now()}: ERROR - Using local folder: {BASE_UPLOAD_FOLDER}, Error: {e}\n")

# Define category-based folder structure
UPLOAD_CATEGORIES = {
    'images': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'images'),
        'extensions': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'svg', 'webp'}
    },
    'documents': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'documents'),
        'extensions': {'txt', 'pdf', 'zip', 'docx', 'xlsx', 'md', 'rtf', 'odt', 'ods'}
    },
    'code': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'code'),
        'extensions': {'py', 'js', 'css', 'html', 'json', 'cpp', 'c', 'h', 'hpp', 'java', 'php', 'rb', 'go', 'rs', 'ts', 'jsx', 'tsx', 'vue', 'sh', 'bat', 'ps1'}
    },
    'robotics': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'robotics'),
        'extensions': {'urdf', 'stl', 'step', 'iges', 'usd', 'obj', 'dae', 'mesh', 'sdf', 'xacro'}
    },
    'configs': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'configs'),
        'extensions': {'cfg', 'yaml', 'yml', 'xml', 'conf', 'ini', 'toml', 'env', 'properties'}
    },
    'models': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'models'),
        'extensions': {'pt', 'pth', 'onnx', 'h5', 'ckpt', 'pkl', 'joblib', 'model', 'weights', 'pb'}
    },
    'videos': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'videos'),
        'extensions': {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'm4v', '3gp'}
    },
    'audio': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'audio'),
        'extensions': {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus'}
    },
    'media': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'media'),
        'extensions': {'psd', 'ai', 'eps', 'indd', 'sketch', 'fig', 'blend', 'max', '3ds', 'fbx', 'dxf', 'dwg'}
    },
    'docker': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'docker'),
        'extensions': {'dockerfile', 'dockerignore', 'docker-compose'}
    },
    'debs': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'debs'),
        'extensions': {'deb', 'rpm', 'pkg', 'dmg', 'msi', 'exe', 'appimage', 'snap', 'flatpak'}
    },
    'scripts': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'scripts'),
        'extensions': {'bash', 'zsh', 'fish', 'csh', 'tcsh', 'ksh', 'pwsh', 'cmd'}
    },
    'test_samples': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'test_samples'),
        'extensions': {'test', 'sample', 'example', 'demo', 'spec', 'fixture'}
    },
    'misc': {
        'folder': os.path.join(BASE_UPLOAD_FOLDER, 'misc'),
        'extensions': set()  # For any other file types
    }
}

# Team documentation integration
TEAM_DOCS_PATH = '/media/mbwh/pop/team_ws/docs'

def scan_team_documentation():
    """Scan team documentation folder and extract metadata"""
    docs = []
    if not os.path.exists(TEAM_DOCS_PATH):
        return docs
    
    try:
        # Scan for markdown files
        md_files = glob.glob(os.path.join(TEAM_DOCS_PATH, '*.md'))
        
        for file_path in md_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract title (first # heading or filename)
                title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                title = title_match.group(1) if title_match else os.path.basename(file_path).replace('.md', '').replace('_', ' ').title()
                
                # Extract description (first paragraph after title)
                description_match = re.search(r'^#.*?\n\n(.+?)(?:\n\n|\n#|$)', content, re.MULTILINE | re.DOTALL)
                description = description_match.group(1).strip()[:200] + "..." if description_match else "Team documentation file"
                
                # Get file stats
                stat = os.stat(file_path)
                modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                
                docs.append({
                    'title': title,
                    'description': description,
                    'file_path': file_path,
                    'filename': os.path.basename(file_path),
                    'modified': modified,
                    'size': stat.st_size
                })
                
            except Exception as e:
                # Log error but continue with other files
                with open('upload_debug.log', 'a') as log:
                    log.write(f"{datetime.datetime.now()}: ERROR scanning {file_path}: {e}\n")
                continue
                
    except Exception as e:
        with open('upload_debug.log', 'a') as log:
            log.write(f"{datetime.datetime.now()}: ERROR accessing team docs: {e}\n")
    
    return docs

def get_team_doc_content(filename):
    """Get the content of a specific team documentation file"""
    file_path = os.path.join(TEAM_DOCS_PATH, filename)
    if not os.path.exists(file_path) or not file_path.startswith(TEAM_DOCS_PATH):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        with open('upload_debug.log', 'a') as log:
            log.write(f"{datetime.datetime.now()}: ERROR reading {file_path}: {e}\n")
        return None

# Create all category folders
os.makedirs(BASE_UPLOAD_FOLDER, exist_ok=True)
for category_info in UPLOAD_CATEGORIES.values():
    os.makedirs(category_info['folder'], exist_ok=True)

# Create a flat set of all allowed extensions for backward compatibility
ALLOWED_EXTENSIONS = set()
for category_info in UPLOAD_CATEGORIES.values():
    ALLOWED_EXTENSIONS.update(category_info['extensions'])

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins
socketio = SocketIO(app, cors_allowed_origins="*")

# === AUTHENTICATION CONFIGURATION ===
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Try to read password directly from .env file if environment variable is not set
APP_PASSWORD = os.environ.get('APP_PASSWORD')
if not APP_PASSWORD or APP_PASSWORD == 'your_secure_password_here':
    try:
        env_path = '/media/mbwh/pop/tvp_ws/local_chat_app/.env'
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('APP_PASSWORD='):
                        APP_PASSWORD = line.strip().split('=', 1)[1]
                        break
    except Exception as e:
        with open('auth_debug.log', 'a') as log:
            log.write(f"{datetime.datetime.now()}: Error reading .env file: {e}\n")

# Fallback to default if still not set
if not APP_PASSWORD:
    APP_PASSWORD = 'your_secure_password_here'

MAX_ATTEMPTS = 5
LOCK_MS = 30000  # 30 seconds lockout
allowedIps = set()

# Debug logging to help troubleshoot password issues
with open('auth_debug.log', 'a') as log:
    log.write(f"{datetime.datetime.now()}: APP_PASSWORD is set: {bool(APP_PASSWORD and APP_PASSWORD != 'your_secure_password_here')}\n")
    log.write(f"{datetime.datetime.now()}: APP_PASSWORD length: {len(APP_PASSWORD) if APP_PASSWORD else 0}\n")
    log.write(f"{datetime.datetime.now()}: APP_PASSWORD value: {APP_PASSWORD[:4]}... (for debugging)\n")

# Motivational quotes for login page
QUOTES = [
    "Code is poetry written in logic.",
    "Debugging is twice as hard as writing the code in the first place.",
    "The best error message is the one that never shows up.",
    "Talk is cheap. Show me the code.",
    "First, solve the problem. Then, write the code.",
    "Code never lies, comments sometimes do.",
    "Programming isn't about what you know; it's about what you can figure out.",
    "The most important property of a program is whether it accomplishes the intention of its user."
]

app.config['UPLOAD_FOLDER'] = BASE_UPLOAD_FOLDER

# === AUTHENTICATION MIDDLEWARE ===
def require_auth():
    """Check if user is authenticated, redirect to login if not"""
    # Get the real IP address (handle proxy headers)
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()
    ip = ip.replace('::ffff:', '')  # Handle IPv4-mapped IPv6
    
    # Check if IP is whitelisted or session is authorized
    if ip in allowedIps or session.get('authorized'):
        return None
    
    return redirect(url_for('login'))

@app.before_request
def check_auth():
    """Apply authentication to all routes except login/logout and SocketIO"""
    # Skip authentication for these endpoints and paths
    if (request.endpoint in ['login', 'login_post', 'static'] or 
        request.path.startswith('/socket.io/') or 
        request.path.startswith('/static/') or
        request.path == '/favicon.ico'):
        return
    
    # Also skip auth for AJAX/API requests from authenticated sessions
    if request.path.startswith('/api/') and session.get('authorized'):
        return
        
    auth_check = require_auth()
    if auth_check:
        return auth_check

# Configuration for persistent storage
CHAT_HISTORY_FILE = "chat_history.json"
MAX_MESSAGES = 50           # Maximum number of messages to store
MESSAGE_EXPIRY_DAYS = 30       # Purge messages older than 5 days

# Define a file to store the tech manual entries.
TECH_MANUAL_FILE = "tech_manual.json"


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_category(filename):
    """Determine the category of a file based on its extension."""
    if not '.' in filename:
        return 'misc'
    
    extension = filename.rsplit('.', 1)[1].lower()
    
    for category, info in UPLOAD_CATEGORIES.items():
        if extension in info['extensions']:
            return category
    
    return 'misc'  # Default category for unrecognized extensions

def get_upload_folder_for_category(category):
    """Get the upload folder path for a specific category."""
    return UPLOAD_CATEGORIES.get(category, UPLOAD_CATEGORIES['misc'])['folder']

def load_tech_manual():
    if os.path.exists(TECH_MANUAL_FILE):
        with open(TECH_MANUAL_FILE, "r") as f:
            return json.load(f)
    return []

def save_tech_manual(data):
    with open(TECH_MANUAL_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_chat_history():
    """Load chat history from a local JSON file and purge expired messages."""
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r") as f:
                data = json.load(f)
            now = datetime.datetime.utcnow()
            # Filter out messages older than MESSAGE_EXPIRY_DAYS
            valid_history = [
                entry for entry in data
                if (now - datetime.datetime.fromisoformat(entry["timestamp"])).days < MESSAGE_EXPIRY_DAYS
            ]
            return valid_history
        except Exception as e:
            print("Error loading chat history:", e)
    return []

def save_chat_history(history):
    """Save the chat history to a local JSON file."""
    try:
        with open(CHAT_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print("Error saving chat history:", e)

# Load persistent chat history on server start
chat_history = load_chat_history()

# === AUTHENTICATION ROUTES ===
@app.route('/login')
def login():
    """Login page with animated gradient and error handling"""
    q = QUOTES[int(time.time()) % len(QUOTES)]  # Deterministic quote selection
    
    err_type = request.args.get('err')  # 'bad' | 'locked' | undefined
    left = int(request.args.get('left', 0))
    ms_remaining = int(request.args.get('ms', 0))
    
    err_html = ''
    if err_type == 'bad':
        attempt_text = f" — {left} attempt{'s' if left != 1 else ''} left" if left else ""
        err_html = f'<div class="err">Incorrect password{attempt_text}.</div>'
    elif err_type == 'locked':
        err_html = f'<div class="err">Too many attempts. Try again in {ms_remaining // 1000}s.</div>'
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>MBWH IntraChat – Login</title>
<style>
:root {{
  --bg1:#0e1117; --bg2:#151a23; --bg3:#1c2430;
  --card: rgba(30,34,45,.92);
  --fg:#f5f7fa; --muted:#97a5b8;
  --acc:#00adb5;
  --border:#2d3444;
  --input-bg:#141a24; --input-border:#394259;
  --btn-bg:#00adb5; --btn-border:#394259;
}}
*{{ box-sizing:border-box; font-family:"Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
body{{
  margin:0; min-height:100vh; color:var(--fg); display:flex; align-items:center; justify-content:center; padding:2rem;
  background:
    radial-gradient(1000px 700px at 20% 20%, var(--bg3), transparent 60%),
    radial-gradient(1000px 700px at 80% 80%, var(--bg2), transparent 60%),
    linear-gradient(120deg, var(--bg1), var(--bg2));
  background-size:200% 200%;
  animation:bg-pan 28s ease-in-out infinite alternate;
}}
@keyframes bg-pan{{ 0%{{background-position:0% 0%}} 100%{{background-position:100% 100%}} }}
.card{{
  background:var(--card); border:1px solid var(--border); border-radius:16px;
  padding:2.5rem 2rem; max-width:420px; width:100%;
  box-shadow:0 20px 40px rgba(0,0,0,.4);
}}
h1{{
  margin:0 0 .5rem; font-size:1.9rem; font-weight:600; text-align:center;
  background:linear-gradient(45deg, var(--acc), #6ea0e0);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}}
.subtitle{{ text-align:center; color:var(--muted); font-size:.95rem; margin:0 0 1.75rem; }}
form{{ display:flex; flex-direction:column; gap:1.1rem; }}
label{{ font-size:.75rem; text-transform:uppercase; letter-spacing:.05em; font-weight:600; color:var(--muted); }}
input[type=password]{{
  width:100%; padding:.75rem 1rem; border-radius:10px; border:1px solid var(--input-border);
  background:var(--input-bg); color:var(--fg); font-size:1rem; outline:none;
  transition:border-color .18s, box-shadow .18s;
}}
input[type=password]:focus{{ border-color:var(--acc); box-shadow:0 0 0 2px rgba(0,173,181,.35); }}
button{{
  padding:.8rem 1rem; border-radius:10px; border:1px solid var(--btn-border);
  background:var(--btn-bg); color:#fff; font-size:1rem; font-weight:600; cursor:pointer;
  transition:background .18s, transform .1s;
}}
button:hover{{ background:#007a85; }}
button:active{{ transform:translateY(1px); }}
.err{{ color:#ff6b6b; font-size:.9rem; text-align:center; margin-top:.25rem; font-weight:600; }}
.note{{ font-size:.8rem; color:var(--muted); text-align:center; margin-top:.6rem; font-style:italic; }}
footer{{ margin-top:1.2rem; text-align:center; color:var(--muted); font-size:.75rem; }}
.badge{{ display:inline-block; background:rgba(255,255,255,.08); border:1px solid var(--border);
  padding:.35rem .75rem; border-radius:999px; font-size:.75rem; }}
@media (max-width:520px){{ body{{padding:1rem;}} .card{{padding:2rem 1.25rem;}} }}
</style>
</head>
<body>
  <div class="card"{' aria-live="polite"' if err_html else ''}>
    <h1>MBWH IntraChat</h1>
    <p class="subtitle">Secure Workspace Access</p>
    <form method="POST" action="/login" autocomplete="off">
      <div>
        <label for="pw">Password</label>
        <input id="pw" type="password" name="password" placeholder="Enter password" autofocus required />
      </div>
      <button type="submit">Enter Workspace</button>
      {err_html}
      <div class="note">"{q}"</div>
    </form>
    <footer><span class="badge">Private</span></footer>
  </div>
</body>
</html>'''

@app.route('/login', methods=['POST'])
def login_post():
    """Handle login with throttling and lockout"""
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()
    ip = ip.replace('::ffff:', '')
    
    now = int(time.time() * 1000)  # Current time in milliseconds
    
    # Initialize login tracking in session
    if 'login' not in session:
        session['login'] = {'attempts': 0, 'lockedUntil': 0}
    
    # Check if account is locked
    if session['login']['lockedUntil'] and session['login']['lockedUntil'] > now:
        ms = session['login']['lockedUntil'] - now
        return redirect(url_for('login', err='locked', ms=ms))
    
    password = (request.form.get('password') or '').strip()
    is_correct = password == APP_PASSWORD
    
    # Debug logging
    with open('auth_debug.log', 'a') as log:
        log.write(f"{datetime.datetime.now()}: Login attempt from {ip}\n")
        log.write(f"{datetime.datetime.now()}: Password length provided: {len(password)}\n")
        log.write(f"{datetime.datetime.now()}: Password matches: {is_correct}\n")
    
    if is_correct:
        # Success: clear counters, whitelist IP, authorize session
        session['login'] = {'attempts': 0, 'lockedUntil': 0}
        allowedIps.add(ip)
        session['authorized'] = True
        return redirect(url_for('index'))
    
    # Failure: increment attempts, maybe lock
    session['login']['attempts'] = session['login'].get('attempts', 0) + 1
    
    if session['login']['attempts'] >= MAX_ATTEMPTS:
        session['login']['lockedUntil'] = now + LOCK_MS
        return redirect(url_for('login', err='locked', ms=LOCK_MS))
    
    # Gentle delay (throttling): grows with attempts, capped at 1.5s
    delay = min(0.2 * session['login']['attempts'], 1.5)
    time.sleep(delay)
    
    left = MAX_ATTEMPTS - session['login']['attempts']
    return redirect(url_for('login', err='bad', left=left))

@app.route('/logout')
def logout():
    """Logout: destroy session and remove IP from whitelist"""
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()
    ip = ip.replace('::ffff:', '')
    
    # Remove IP from allowed list
    allowedIps.discard(ip)
    
    # Clear session
    session.clear()
    
    return redirect(url_for('login'))

# === MAIN APPLICATION ROUTES ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    # Reload persistent chat history so the history page reflects the stored data.
    global chat_history
    chat_history = load_chat_history()
    return render_template('history.html', chat_history=chat_history)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error':'No file part'}), 400
    f = request.files['file']
    if f.filename == '' or not allowed_file(f.filename):
        return jsonify({'error':'Invalid filename'}), 400

    # Determine file category and get appropriate folder
    category = get_file_category(f.filename)
    upload_folder = get_upload_folder_for_category(category)
    
    # make the filename unique
    name = secure_filename(f"{datetime.datetime.utcnow().timestamp()}_{f.filename}")
    save_path = os.path.join(upload_folder, name)
    
    # Ensure the category folder exists
    os.makedirs(upload_folder, exist_ok=True)
    f.save(save_path)
    
    # Log upload info to file for debugging
    with open('upload_debug.log', 'a') as log:
        log.write(f"{datetime.datetime.now()}: UPLOAD - {f.filename} -> {save_path} (category: {category})\n")

    # build URL - include category in the path
    url = url_for('uploaded_file', category=category, filename=name)
    return jsonify({
        'url': url, 
        'name': f.filename, 
        'category': category,
        'saved_as': name,
        'full_path': save_path  # Adding this for debugging
    }), 200


@app.route('/api/team-docs')
def get_team_docs():
    """API endpoint to get list of team documentation"""
    try:
        docs = scan_team_documentation()
        return jsonify({
            'success': True,
            'docs': docs,
            'count': len(docs)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/team-docs/<filename>')
def get_team_doc(filename):
    """API endpoint to get content of a specific team document"""
    try:
        content = get_team_doc_content(filename)
        if content is None:
            return jsonify({
                'success': False,
                'error': 'Document not found'
            }), 404
        
        return jsonify({
            'success': True,
            'filename': filename,
            'content': content
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/docs')
def docs_browser():
    """Render the team documentation browser page"""
    try:
        docs = scan_team_documentation()
        with open('upload_debug.log', 'a') as log:
            log.write(f"{datetime.datetime.now()}: DOCS REQUEST - Found {len(docs)} documents\n")
        return render_template('docs.html', docs=docs)
    except Exception as e:
        with open('upload_debug.log', 'a') as log:
            log.write(f"{datetime.datetime.now()}: DOCS ERROR: {e}\n")
        return f"Error loading docs: {e}", 500

@app.route('/manual')
def manual():
    """
    Renders the Tech Manual page. If ?q=term is provided, filters entries.
    """
    # load all entries
    tech_manual = load_tech_manual()
    
    # Get team documentation
    team_docs = scan_team_documentation()
    
    # Convert team docs to manual format for unified search
    for doc in team_docs:
        tech_manual.append({
            'message': f"📋 **{doc['title']}**\n\n{doc['description']}\n\n*Team Documentation - {doc['filename']}*",
            'category': 'Team Docs',
            'username': 'System',
            'timestamp': doc['modified'],
            'is_team_doc': True,
            'filename': doc['filename'],
            'file_path': doc['file_path']
        })

    # optional reverse‐search via query param “q”
    q = request.args.get('q', '').strip().lower()
    if q:
        tech_manual = [
            e for e in tech_manual
            if q in e.get('message','').lower()
            or q in e.get('category','').lower()
            or q in e.get('username','').lower()
        ]

    # pass both entries and the search term back to template
    return render_template('manual.html',
                           entries=tech_manual,
                           query=q,
                           team_docs_count=len(team_docs))


@socketio.on('connect')
def handle_connect():
    # Send the entire persistent chat history to the newly connected client
    send(json.dumps(chat_history), broadcast=False)

@socketio.on('message')
def handle_message(msg):
    print(f"Message: {msg}")
    # For simplicity, assume the incoming msg is a string like "username: message"
    # Create an entry with a timestamp.
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "msg": msg
    }
    chat_history.append(entry)
    
    # Enforce a maximum cap on stored messages
    if len(chat_history) > MAX_MESSAGES:
        chat_history[:] = chat_history[-MAX_MESSAGES:]
    
    # Save updated history to disk
    save_chat_history(chat_history)
    
    # Broadcast the new message (as a JSON string)
    send(json.dumps(entry), broadcast=True)

@app.route('/export', methods=['POST'])
def export_message():
    """
    Expects a JSON payload of the form:
    {
      "message": "sam run command: python script.py",
      "category": "sam run command",
      "username": "TVP",
      "timestamp": "2025-04-11T12:34:56"
    }
    """
    payload = request.get_json()
    
    # If no timestamp is included, add the current UTC time.
    if "timestamp" not in payload:
        payload["timestamp"] = datetime.datetime.utcnow().isoformat()

    # Load any existing entries, append the new one, and save.
    tech_manual = load_tech_manual()
    tech_manual.append(payload)
    save_tech_manual(tech_manual)
    
    return jsonify({"status": "ok", "message": "Message exported to Tech Manual."})

# AI Stack:
# AI Summarization endoint
@app.route('/summarize', methods=['POST'])
def summarize_endpoint():
    data = request.get_json()
    if 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
    text = data['text']
    # You can adjust max_length and min_length as needed
    summary = summarize_text(text, max_length=150, min_length=40)
    return jsonify({"summary": summary}), 200

@socketio.on('alert')
def handle_alert(alert_msg):
    print("Alert received:", alert_msg)
    # Broadcast the alert message to all clients with an "alert" flag.
    send(json.dumps({"msg": "ALERT: " + alert_msg, "alert": True}), broadcast=True)

@app.route('/debug-config', methods=['GET'])
def debug_config():
    """Return current upload configuration for debugging."""
    return jsonify({
        'preferred_folder': PREFERRED_UPLOAD_FOLDER,
        'local_folder': LOCAL_UPLOAD_FOLDER,
        'current_base_folder': BASE_UPLOAD_FOLDER,
        'using_team_workspace': BASE_UPLOAD_FOLDER == PREFERRED_UPLOAD_FOLDER,
        'categories': {
            category: {
                'folder': info['folder'],
                'extensions': list(info['extensions']),
                'exists': os.path.exists(info['folder'])
            }
            for category, info in UPLOAD_CATEGORIES.items()
        }
    })

@app.route('/upload-categories', methods=['GET'])
def get_upload_categories():
    """Return information about available upload categories."""
    categories_info = {}
    for category, info in UPLOAD_CATEGORIES.items():
        categories_info[category] = {
            'extensions': list(info['extensions']),
            'folder_path': info['folder']
        }
    return jsonify(categories_info)

@app.route('/uploads/<category>/<filename>')
def uploaded_file(category, filename):
    """Serve uploaded files from category-specific folders."""
    upload_folder = get_upload_folder_for_category(category)
    return send_from_directory(upload_folder, filename)

@app.route('/uploads/<filename>')
def uploaded_file_legacy(filename):
    """Legacy route for backward compatibility - looks in the base upload folder."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)




if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5656, debug=True, allow_unsafe_werkzeug=True)


