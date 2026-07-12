<div align="center">

# 💬 Intra-Chat

**A self-hosted, real-time chat for your team's local network — with file
sharing, a searchable command manual, a shared brain-dump board, personal
workspaces, a project knowledge base, a lab-equipment inventory, an agent
API, and an optional local-LLM summariser.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000.svg)](https://flask.palletsprojects.com/)
[![Socket.IO](https://img.shields.io/badge/Socket.IO-realtime-010101.svg)](https://socket.io/)
[![Local-first](https://img.shields.io/badge/local--first-LAN-22f5ff.svg)](#)

<sub>No accounts. No cloud. No tracking. One Python process and a browser.</sub>

<br/>

![Intra-Chat hero](docs/screenshots/06-notifications.png)

</div>

---

## Why Intra-Chat?

Most team-chat tools assume the cloud. Intra-Chat assumes the opposite:
**a single Python process on your LAN**, accessed by everyone over a browser.
No SaaS subscriptions, no third-party servers, no data leaving your network.

It started as an internal tool for a robotics team that wanted a place to:

- 🚀 Drop **commands and snippets** into a shared scrollback that doesn't
  vanish when Slack forgets it.
- 📚 Pin the good stuff into a **searchable tech manual** with one keystroke.
- 🧠 Capture half-baked ideas in a **brain-dump board** with reactions and
  tags — independent from the chat noise.
- 🔔 Stay aware via **real-time notifications** (with sound + browser push)
  when teammates publish something worth seeing.
- 🤖 Get **AI summaries** of long conversations using a model running on
  your own machine (Ollama).

It is intentionally small. One file (`app.py`), one HTML template per
feature, JSON files for storage. The whole thing fits in your head.

## Features

|   | Feature | What it does |
|---|---------|--------------|
| 💬 | **Real-time chat** | Socket.IO-powered, persistent across reloads, message history with sane retention. |
| 📁 | **Smart file uploads** | Drag-and-drop with auto-categorisation across 14 buckets (code, images, robotics, configs, models, …). |
| 📒 | **Tech manual** | Press `Ctrl+E` on any chat message to pin it into a searchable reference book with a category. |
| 🧠 | **Brain dump board** | Long-form, taggable, reaction-able knowledge entries. Public to the team by default, export as Markdown. |
| 🗂️ | **Personal workspaces** | Per-member sign-in with a personal passcode. Organise notes into **projects**, keep them private or share with the team. Toggle a whole project public in one click. |
| 📚 | **Project knowledge base** | Searchable, tagged knowledge entries grouped by project — the durable memory behind the chat noise. |
| 📦 | **Lab equipment inventory** | Track assets with **printable, meaningful tags** (e.g. `LAB138-SEN-0003` = lab no · category · procurement order), an **In-charge** owner picked from your team roster, and statuses (Available / In Use / Borrowed / Lost / Retired / Broken). Check-out / check-in with history, CSV/Markdown export. |
| 🤖 | **Agent / API integration** | Issue scoped **API keys** so coding agents and scripts can push knowledge programmatically. See [docs/AGENT_INTEGRATION.md](docs/AGENT_INTEGRATION.md). |
| 🔔 | **Live notifications** | Toast + bell badge + browser notifications on every new brain-dump or system event. |
| 🚨 | **Broadcast alerts** | `/alert your message` plays a sound for every connected client — perfect for "build's broken". |
| 📚 | **Team docs** | Point `TEAM_DOCS_PATH` at a folder of `.md` files and they show up at `/docs` and inside the manual search. |
| 🤖 | **AI summarise** | `/summarize` calls a local [Ollama](https://ollama.com) model. No API keys. No data leaves your box. |
| 🔐 | **Auth** | Single shared password + per-member passcodes + IP allow-listing + lockout-on-brute-force. |
| ⌨️ | **Power-user shortcuts** | `Ctrl+H/M/U/E/B/L`, slash-commands, copy-with-username-stripped, message export, … |
| 📱 | **Mobile-friendly** | Fully responsive — every page (chat, workspace, inventory, knowledge, manual, API keys) adapts to phones and small screens. |

## Screenshots

<table>
<tr>
<td align="center" width="50%"><b>Login</b><br/><img src="docs/screenshots/01-login.png" alt="Login"/></td>
<td align="center" width="50%"><b>Chat</b><br/><img src="docs/screenshots/02-chat.png" alt="Chat"/></td>
</tr>
<tr>
<td align="center"><b>History</b><br/><img src="docs/screenshots/03-history.png" alt="History"/></td>
<td align="center"><b>Tech Manual</b><br/><img src="docs/screenshots/04-manual.png" alt="Tech Manual"/></td>
</tr>
<tr>
<td align="center"><b>Brain Dump</b><br/><img src="docs/screenshots/05-braindump.png" alt="Brain Dump"/></td>
<td align="center"><b>Notifications</b><br/><img src="docs/screenshots/06-notifications.png" alt="Notifications"/></td>
</tr>
</table>

### Workspaces & project knowledge base

Every member gets a personal workspace. Organise notes into **projects**,
keep them private or flip a whole project **Public** to share it on the team
board. Each project is its own searchable, taggable knowledge base.

<table>
<tr>
<td align="center" width="50%"><b>My Workspace</b><br/><img src="docs/screenshots/07-workspace.png" alt="Personal workspace with projects"/></td>
<td align="center" width="50%"><b>Knowledge base</b><br/><img src="docs/screenshots/08-knowledge.png" alt="Project knowledge base entries"/></td>
</tr>
</table>

### Lab equipment inventory

Track assets with **printable, meaningful tags** (`LAB138-SEN-0003` = lab no ·
category · procurement order), an **In-charge** owner picked from your team
roster, and a full status set (Available / In Use / Borrowed / Lost / Retired
/ Broken). Check-out / check-in with history and CSV/Markdown export.

<table>
<tr>
<td align="center" width="60%"><b>Inventory</b><br/><img src="docs/screenshots/09-inventory.png" alt="Lab equipment inventory"/></td>
<td align="center" width="40%"><b>On a phone</b><br/><img src="docs/screenshots/11-mobile.png" alt="Inventory on a mobile screen"/></td>
</tr>
</table>

### Agent / API integration

Mint scoped **API keys** so coding agents and scripts can push knowledge into
a project programmatically — no browser required.

<p align="center"><img src="docs/screenshots/10-api-keys.png" alt="Agent API key management" width="80%"/></p>

> Want to record a GIF for your own fork? Drop it in `docs/screenshots/` and
> reference it here.

## Quick start

```bash
git clone https://github.com/tvpian/Intra-Chat.git
cd Intra-Chat

python -m pip install -r requirements.txt
python setup_password.py        # interactive — writes .env
python app.py                   # http://localhost:5656
```

That's the whole installation. Open the URL in any browser on your LAN, type
the password you just chose, and you're in.

> **Heads up:** `setup_password.py` sets `chmod 600` on the resulting `.env`.
> It contains your login password and a Flask session signing key — don't
> commit it.

## Configuration

All configuration lives in `.env`. Copy [.env.example](.env.example) and edit
the values you care about. The most useful options:

| Variable          | Default                  | Purpose                                                |
| ----------------- | ------------------------ | ------------------------------------------------------ |
| `APP_PASSWORD`    | _(required)_             | Shared login password                                  |
| `SECRET_KEY`      | random per launch        | Flask session signing key                              |
| `HOST` / `PORT`   | `0.0.0.0` / `5656`       | Bind address                                           |
| `UPLOAD_FOLDER`   | `<repo>/uploads`         | Where uploaded files are stored                        |
| `TEAM_DOCS_PATH`  | _(unset)_                | Optional folder of `.md` files exposed in `/docs`      |
| `OLLAMA_HOST`     | `http://localhost:11434` | Local Ollama server URL                                |
| `OLLAMA_MODEL`    | `llama3.2`               | Model used by `/summarize`                             |
| `MAX_ATTEMPTS`    | `5`                      | Failed login lockout threshold                         |
| `LOCK_MS`         | `30000`                  | Lockout duration in milliseconds                       |
| `LAB_NO`          | `138`                    | Lab number embedded in printable inventory asset tags  |
| `TEAM_ROSTER`     | _(unset)_                | Comma-separated extra names for the inventory In-charge picker |
| `DEBUG_LOGS`      | `0`                      | Set `1` to write upload/auth debug logs to disk        |

## Optional: local AI with Ollama

The `/summarize` chat command calls a model on **your machine** through
Ollama. If Ollama isn't running, the command degrades gracefully with an
explanatory message — the rest of the app keeps working.

```bash
# install once: https://ollama.com
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2          # or mistral, qwen2.5, gemma3, …
ollama serve
```

Switch the model at any time by setting `OLLAMA_MODEL` in `.env`.

## Agent & API integration

Beyond the browser UI, Intra-Chat exposes a small HTTP API so coding agents
and scripts can push knowledge into a project automatically. Mint a scoped
key at `/admin/api-keys` (or `POST /api/keys`), then authenticate with
`Authorization: Bearer <key>`.

```bash
export INTRA_CHAT_URL="http://localhost:5656"
export INTRA_CHAT_KEY="ic_<project>_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export INTRA_CHAT_PROJECT="<project>"

python3 scripts/kb_push.py --title "Deploy steps" --file NOTES.md
```

Keys are shown once and stored only as a hash. Full details, endpoints, and
examples live in [docs/AGENT_INTEGRATION.md](docs/AGENT_INTEGRATION.md).

## Slash commands & shortcuts

Inside the chat box:

| Command           | Effect                                                      |
| ----------------- | ----------------------------------------------------------- |
| `/search <term>`  | Jump straight to the tech manual filtered by `<term>`.      |
| `/docs <term>`    | Open the team-docs browser, filtered.                       |
| `/alert <msg>`    | Broadcast a sound + modal alert to everyone.                |
| `/summarize`      | Send the last ~10 messages to the local LLM for a summary.  |

Keyboard shortcuts (anywhere on the chat page):

| Keys      | Action                              |
| --------- | ----------------------------------- |
| `Enter`   | Send (Shift+Enter for newline)      |
| `Ctrl+H`  | History                             |
| `Ctrl+M`  | Tech manual                         |
| `Ctrl+B`  | Brain dump board                    |
| `Ctrl+U`  | Change username                     |
| `Ctrl+E`  | Export the last message to manual   |
| `Ctrl+L`  | Logout                              |
| `↑`/`↓`   | Scroll messages                     |

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │            Browser (LAN)            │
                     │  ┌─────────────────────────────┐    │
                     │  │ index.html / Socket.IO JS   │    │
                     │  └────────────┬────────────────┘    │
                     └───────────────│─────────────────────┘
                                     │  WebSocket + HTTP
                     ┌───────────────▼─────────────────────┐
                     │      app.py — Flask + Socket.IO     │
                     │  ┌────────┐ ┌────────┐ ┌─────────┐  │
                     │  │  auth  │ │ uploads│ │ summary │──┼──► Ollama
                     │  └────────┘ └────────┘ └─────────┘  │     (local)
                     │  ┌────────┐ ┌────────┐ ┌─────────┐  │
                     │  │ manual │ │ brain  │ │  notif  │  │
                     │  └────────┘ └────────┘ └─────────┘  │
                     └────────────────┬────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │   JSON files   │
                              │  (chat, manual,│
                              │  braindump,    │
                              │  notifications)│
                              └────────────────┘
```

Storage is intentionally JSON-on-disk — easy to inspect, back up, and migrate.
A future SQLite backend would be a welcome contribution.

## Deployment

For a long-running LAN deployment, use the included systemd template:

```bash
sudo cp intra_chat.service.template /etc/systemd/system/intra_chat.service
sudo $EDITOR /etc/systemd/system/intra_chat.service     # set User + paths

sudo systemctl daemon-reload
sudo systemctl enable --now intra_chat
sudo journalctl -u intra_chat -f
```

Full deployment notes (reverse proxy, security checklist, etc.) live in
[DEPLOYMENT.md](DEPLOYMENT.md).

## Project layout

```
Intra-Chat/
├── app.py                      # Flask + Socket.IO entrypoint, all routes
├── ai_engine.py                # Ollama wrapper for /summarize
├── setup_password.py           # Interactive .env generator
├── requirements.txt
├── .env.example                # Documented env-var template
├── intra_chat.service.template # systemd unit template
├── templates/
│   ├── index.html              # Main chat UI
│   ├── login.html
│   ├── history.html
│   ├── manual.html
│   ├── docs.html
│   ├── braindump.html
│   ├── workspace.html          # Personal workspaces & projects
│   ├── knowledge.html          # Project knowledge base
│   ├── inventory.html          # Lab equipment inventory
│   └── api_keys.html           # Agent API-key management
├── scripts/
│   ├── kb_push.py              # Push knowledge via the API
│   └── kb_demo.sh              # End-to-end API demo
├── docs/
│   ├── AGENT_INTEGRATION.md    # Agent/API guide
│   └── screenshots/            # README assets
├── static/                     # alert.mp3, fonts, etc.
└── uploads/                    # File storage (auto-categorised)
```

## Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for ground
rules — short version: keep it small, keep it local, no heavy deps.

Areas where help is especially welcome:

- 🗄️ Optional SQLite backend (currently JSON files)
- 🔌 More AI backends (`OpenAI`, `llama.cpp`, …) behind `ai_engine.py`
- 🎨 Theming / light mode
- 🌐 i18n for the UI strings
- ✅ Tests

## License

[MIT](LICENSE) © 2026 [tvpian](https://github.com/tvpian)

---

<div align="center">
<sub>Built with Flask, Socket.IO, and a healthy distrust of the cloud.</sub>
</div>
