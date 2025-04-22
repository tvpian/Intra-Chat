from flask import Flask, render_template
from flask_socketio import SocketIO, send
from flask_cors import CORS
import json
import os
import datetime
from flask import Flask, render_template, request, jsonify
import os, json, datetime
from ai_engine import summarize_text  # Import the summarization function
from werkzeug.utils import secure_filename
from flask import send_from_directory, url_for

# just after your existing imports:
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {
    'png','jpg','jpeg','gif',
    'txt','pdf','zip','docx','xlsx',
    # now include code/web formats:
    'py','js','css','html','json','md'
}

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins
socketio = SocketIO(app, cors_allowed_origins="*")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuration for persistent storage
CHAT_HISTORY_FILE = "chat_history.json"
MAX_MESSAGES = 50           # Maximum number of messages to store
MESSAGE_EXPIRY_DAYS = 30       # Purge messages older than 5 days

# Define a file to store the tech manual entries.
TECH_MANUAL_FILE = "tech_manual.json"


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

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

    # make the filename unique
    name = secure_filename(f"{datetime.datetime.utcnow().timestamp()}_{f.filename}")
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], name)
    f.save(save_path)

    # build URL
    url = url_for('uploaded_file', filename=name)
    return jsonify({'url': url, 'name': f.filename}), 200


@app.route('/manual')
def manual():
    """
    Renders the Tech Manual page. If ?q=term is provided, filters entries.
    """
    # load all entries
    tech_manual = load_tech_manual()

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
                           query=q)


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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)




if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5656, debug=True, allow_unsafe_werkzeug=True)


