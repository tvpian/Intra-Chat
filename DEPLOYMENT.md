# Deployment Guide

Intra-Chat is a single Flask-SocketIO app. The simplest deployment is just
`python app.py` behind a firewall on your LAN. For long-running setups, use
the systemd service template included in this repo.

## 1. Quick local run

```bash
git clone https://github.com/tvpian/Intra-Chat.git
cd Intra-Chat
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python setup_password.py     # creates .env with password + secret key
python app.py                # http://localhost:5656
```

## 2. Configure

All configuration lives in `.env`. See [.env.example](.env.example) for the
full list of options. The most useful ones:

| Variable           | Default               | Purpose                                     |
| ------------------ | --------------------- | ------------------------------------------- |
| `APP_PASSWORD`     | _required_            | Login password                              |
| `SECRET_KEY`       | random per launch     | Flask session signing key                   |
| `HOST` / `PORT`    | `0.0.0.0` / `5656`    | Bind address                                |
| `UPLOAD_FOLDER`    | `<repo>/uploads`      | Where uploaded files are stored             |
| `TEAM_DOCS_PATH`   | _(unset)_             | Optional folder of `.md` files to expose    |
| `OLLAMA_HOST`      | `http://localhost:11434` | Local Ollama server URL                  |
| `OLLAMA_MODEL`     | `llama3.2`            | Model used by `/summarize`                  |
| `DEBUG_LOGS`       | `0`                   | Set to `1` to write upload/auth debug logs  |

## 3. Optional: AI summarisation with Ollama

The `/summarize` chat command calls a local Ollama server. To enable it:

```bash
# https://ollama.com
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2          # or any other model you like
ollama serve                  # runs on http://localhost:11434
```

If Ollama is not running, `/summarize` will reply with a helpful error
instead of crashing the chat.

## 4. systemd service (Linux)

```bash
sudo cp intra_chat.service.template /etc/systemd/system/intra_chat.service
sudo $EDITOR /etc/systemd/system/intra_chat.service   # set User + paths

sudo systemctl daemon-reload
sudo systemctl enable --now intra_chat
sudo systemctl status intra_chat
sudo journalctl -u intra_chat -f
```

The service file uses `EnvironmentFile=/path/to/Intra-Chat/.env`, so all
configuration stays in one place.

## 5. Reverse proxy (optional)

If you want HTTPS or a friendlier URL, drop nginx/Caddy in front. Make sure
to forward WebSocket upgrades (Intra-Chat uses Socket.IO).

Minimal nginx snippet:

```nginx
location / {
    proxy_pass http://127.0.0.1:5656;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## 6. Security checklist

- [ ] `APP_PASSWORD` is long (≥ 12 chars).
- [ ] `.env` is `chmod 600` and not committed.
- [ ] Server is on a trusted LAN or behind a VPN/reverse proxy.
- [ ] Uploads folder is on a partition with enough space and reasonable
      permissions.
- [ ] Dependencies are kept up to date (`pip install -U -r requirements.txt`).
