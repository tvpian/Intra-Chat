from flask import Flask, render_template
from flask_socketio import SocketIO, send
from flask_cors import CORS
import json
import os
import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration for persistent storage
CHAT_HISTORY_FILE = "chat_history.json"
MAX_MESSAGES = 50           # Maximum number of messages to store
MESSAGE_EXPIRY_DAYS = 30       # Purge messages older than 5 days

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

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5656, debug=True, allow_unsafe_werkzeug=True)
