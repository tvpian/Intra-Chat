# Deployment Guide

## Quick Setup

1. **Install Dependencies**
   ```bash
   pip install flask flask-socketio flask-cors python-dotenv eventlet
   ```

2. **Set Up Password**
   ```bash
   python setup_password.py
   ```

3. **Run the Application**
   ```bash
   python app.py
   ```
   The app will be available at `http://localhost:5656`

## Production Deployment with Systemd

### 1. Create Service File
Copy the template and customize it:
```bash
cp intra_chat.service.template /etc/systemd/system/intra_chat.service
```

### 2. Edit Service Configuration
Update the following in `/etc/systemd/system/intra_chat.service`:
- `User=YOUR_USERNAME` - Replace with your username
- `WorkingDirectory=/path/to/your/chat/app` - Full path to your app directory
- `Environment=APP_PASSWORD=your_secure_password_here` - Your secure password
- `Environment=SECRET_KEY=your_secret_key_here` - Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `ExecStart=/path/to/python3 /path/to/your/chat/app/app.py` - Full paths to Python and app.py

### 3. Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable intra_chat
sudo systemctl start intra_chat
sudo systemctl status intra_chat
```

### 4. Check Logs
```bash
sudo journalctl -u intra_chat -f
```

## Security Notes

- Keep your `.env` file and actual service files out of version control
- Use strong passwords (8+ characters)
- Consider setting up a reverse proxy (nginx) for HTTPS
- Regularly update dependencies for security patches

## File Structure

```
your-chat-app/
├── app.py                          # Main application
├── .env                           # Your config (create from .env.template)
├── .env.template                  # Template for environment variables
├── intra_chat.service.template    # Template for systemd service
├── setup_password.py              # Password setup utility
├── requirements.txt               # Python dependencies
├── templates/                     # HTML templates
└── static/                        # Static files
```
