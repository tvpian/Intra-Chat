# Agent Integration Guide — Knowledge Base API

This guide shows how each teammate's VS Code Copilot agent (or any script) can
push knowledge from a project into Intra-Chat's Knowledge Base over REST.

Every project gets its **own API key**. That key is the ownership credential:
- Entries you create with it default to **private** (only your key can read/edit them).
- You choose which entries to flip to **team**-visible.
- No other key (and no logged-in browser) can edit or delete your project's entries.

---

## 1. Get an API key (one time, per project)

The easiest way is from your personal workspace:

1. Open the app and log in.
2. Go to **🗂️ My Workspace** (top of the chat page) or visit `/workspace`.
3. Sign in with your name + a personal passcode (first time creates your workspace).
4. Create a project, then click the **🔑 key** button on that project.
5. **Copy the key immediately** — it's shown only once. Format:
   `ic_<project>_<32-hex>`

(Admins can also mint keys at `/admin/api-keys`.)

Store it as an environment variable, never commit it:

```bash
export INTRA_CHAT_URL="http://localhost:5656"   # your server address
export INTRA_CHAT_KEY="ic_nav-stack_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export INTRA_CHAT_PROJECT="nav-stack"
```

---

## 2. The API contract

Base URL: `http://<server>:5656`
Auth header (required for private/project actions):
`Authorization: Bearer <your-api-key>`

### Create an entry — `POST /api/braindump`
```json
{
  "title": "How the costmap layers stack",
  "content": "Full markdown notes here...",
  "tags": ["navigation", "costmap"],
  "project_id": "nav-stack",
  "visibility": "private",        // "private" (default) or "team"
  "author": "nav-stack agent"     // optional
}
```
- `project_id` **must match the key's project**, otherwise `403`.
- Omitting `project_id` (or using `"general"`) posts to the legacy open team board.
- Requests made with only the API key (no browser session) are tagged `source: "agent"`.

### Read your private KB — `GET /api/braindump?mine=1`
Returns only your project's entries (requires your key; `401` without it).

### Read the team board — `GET /api/braindump`
Returns team-visible entries + your own project's entries if your key is sent.

### Update — `PUT /api/braindump/<id>`
Same auth rules. Use it to flip visibility:
```json
{ "visibility": "team" }
```

### Delete — `DELETE /api/braindump/<id>`
Requires the owning project's key.

Filters available on `GET`: `?tag=`, `?author=`, `?project_id=`, `?q=` (text search).

---

## 3. Drop-in sync script

A ready-to-use client lives at [`scripts/kb_push.py`](../scripts/kb_push.py).
Point your agent at it, or call it directly:

```bash
# push a single note
python3 scripts/kb_push.py --title "Deploy steps" --file NOTES.md

# push every markdown file under docs/ as private entries
python3 scripts/kb_push.py --scan docs --tag docs
```

---

## 4. Wiring it into a VS Code Copilot agent

Create a project-local agent file, e.g. `.github/copilot/kb-sync.agent.md`, so the
agent knows how to dump knowledge on request:

```markdown
---
description: Scans this project's knowledge base and pushes it to Intra-Chat.
tools: ['runInTerminal', 'search', 'readFile']
---

When asked to "sync the knowledge base" or "dump to Intra-Chat":
1. Identify the relevant docs / source-of-truth files in this repo.
2. Summarize each into a concise knowledge entry (title + markdown body).
3. For each entry, run:
   `python3 scripts/kb_push.py --title "<title>" --content "<body>" --tag <topic>`
   (the script reads INTRA_CHAT_URL / INTRA_CHAT_KEY / INTRA_CHAT_PROJECT from env)
4. Entries are PRIVATE by default. Only add `--team` for items meant for everyone.
5. Report back which entries were created and their IDs.
```

The agent never needs the raw key in the prompt — it's read from the environment
by `kb_push.py`, keeping the secret out of chat context.
