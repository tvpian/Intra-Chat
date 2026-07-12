#!/usr/bin/env bash
#
# kb_demo.sh — End-to-end demo & self-test for the Knowledge Base feature.
#
# It creates a throwaway "demo-bot" project, exercises every behavior you care
# about, and prints PASS/FAIL for each, so you can confirm things work the way
# you want. By default it targets the live app on localhost:5656.
#
# Usage:
#   ./scripts/kb_demo.sh                 # run the demo (prompts for password)
#   ./scripts/kb_demo.sh --cleanup       # run, then revoke key + delete entries
#   BASE=http://127.0.0.1:5656 ./scripts/kb_demo.sh
#
# The password is read interactively (never shown, never passed as an arg).
# You can also set APP_PASSWORD in the environment to skip the prompt.

set -u
BASE="${BASE:-http://127.0.0.1:5656}"
PROJECT="demo-bot"
COOKIES="$(mktemp)"
CLEANUP=0
[[ "${1:-}" == "--cleanup" ]] && CLEANUP=1

pass=0; fail=0
check() { # check "desc" expected actual
  if [[ "$2" == "$3" ]]; then
    echo "  ✅ PASS: $1  (got $3)"; pass=$((pass+1))
  else
    echo "  ❌ FAIL: $1  (expected $2, got $3)"; fail=$((fail+1))
  fi
}
code() { tail -n1 <<<"$1"; }         # last line = HTTP code
body() { sed '$d' <<<"$1"; }         # everything but last line

# curl helper that appends the HTTP status as a trailing line
req() { curl -s -w $'\n%{http_code}' "$@"; }

cleanup_files() { rm -f "$COOKIES"; }
trap cleanup_files EXIT

echo "== Intra-Chat Knowledge Base demo =="
echo "Target: $BASE"
echo

# ── 1. Login ──────────────────────────────────────────────────────────
if [[ -z "${APP_PASSWORD:-}" ]]; then
  read -r -s -p "App password: " APP_PASSWORD; echo
fi
login=$(req -c "$COOKIES" -X POST "$BASE/login" --data-urlencode "password=$APP_PASSWORD")
lc=$(code "$login")
if [[ "$lc" != "302" && "$lc" != "200" ]]; then
  echo "❌ Login failed (HTTP $lc). Wrong password or server unreachable."; exit 1
fi
echo "[1] Logged in (HTTP $lc)"

# ── 2. Create a demo project API key ──────────────────────────────────
keyres=$(req -b "$COOKIES" -X POST "$BASE/api/keys" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\":\"$PROJECT\",\"label\":\"KB Demo\"}")
kc=$(code "$keyres")
KEY=$(body "$keyres" | python3 -c "import sys,json;print(json.load(sys.stdin).get('api_key',''))" 2>/dev/null)
KEY_ID=$(body "$keyres" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
echo "[2] Created project key for '$PROJECT' (HTTP $kc)"
check "key creation returns 201" 201 "$kc"
check "raw api_key returned once" 1 "$([[ -n "$KEY" ]] && echo 1 || echo 0)"

# ── 3. Key listing must NOT leak the hash ─────────────────────────────
listres=$(req -b "$COOKIES" "$BASE/api/keys")
leak=$(body "$listres" | grep -c "key_hash" || true)
check "key listing hides key_hash" 0 "$leak"

# ── 4. Agent posts a PRIVATE entry (API key only, no session) ─────────
priv=$(req -X POST "$BASE/api/braindump" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"title\":\"Demo private note\",\"content\":\"only $PROJECT should see this\",\"project_id\":\"$PROJECT\",\"visibility\":\"private\",\"tags\":[\"demo\"]}")
pc=$(code "$priv")
PRIV_ID=$(body "$priv" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
PRIV_SRC=$(body "$priv" | python3 -c "import sys,json;print(json.load(sys.stdin).get('source',''))" 2>/dev/null)
echo "[3] Posted a private entry as the agent (HTTP $pc)"
check "private entry created" 201 "$pc"
check "pure-API-key post tagged source=agent" agent "$PRIV_SRC"

# ── 5. Agent posts a TEAM-visible entry ───────────────────────────────
team=$(req -X POST "$BASE/api/braindump" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"title\":\"Demo shared note\",\"content\":\"everyone can see this\",\"project_id\":\"$PROJECT\",\"visibility\":\"team\",\"tags\":[\"demo\"]}")
tc=$(code "$team")
TEAM_ID=$(body "$team" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
check "team entry created" 201 "$tc"

# ── 6. Spoofing: post to the project WITHOUT the key must be rejected ──
spoof=$(req -X POST "$BASE/api/braindump" \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"spoofed\",\"project_id\":\"$PROJECT\"}")
sc=$(code "$spoof")
check "posting to project without its key is blocked" 403 "$sc"

# ── 7. Private entry is HIDDEN from the team board (no key) ────────────
board=$(req "$BASE/api/braindump")
priv_on_board=$(body "$board" | grep -c "$PRIV_ID" || true)
team_on_board=$(body "$board" | grep -c "$TEAM_ID" || true)
check "private entry NOT on public team board" 0 "$priv_on_board"
check "team entry IS on public team board" 1 "$team_on_board"

# ── 8. Owner sees BOTH via mine=1 ─────────────────────────────────────
mine=$(req -H "Authorization: Bearer $KEY" "$BASE/api/braindump?mine=1")
mine_priv=$(body "$mine" | grep -c "$PRIV_ID" || true)
check "owner sees own private entry via mine=1" 1 "$mine_priv"

# ── 9. Ownership: editing the private entry withOUT the key fails ─────
noown=$(req -b "$COOKIES" -X PUT "$BASE/api/braindump/$PRIV_ID" \
  -H "Content-Type: application/json" -d '{"title":"hijacked"}')
nc=$(code "$noown")
check "non-owner (session only) cannot edit private entry" 403 "$nc"

# ── 10. Owner CAN toggle visibility to team ───────────────────────────
tog=$(req -X PUT "$BASE/api/braindump/$PRIV_ID" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"visibility":"team"}')
gc=$(code "$tog")
check "owner can flip private -> team" 200 "$gc"

echo
echo "──────────────────────────────────────────────"
echo "Results:  $pass passed, $fail failed"
echo "Demo entries live under project '$PROJECT'."
echo "View them in the GUI:"
echo "  • Team board:      $BASE/braindump   (shows the 2 shared demo notes)"
echo "  • My Knowledge:    $BASE/knowledge    (paste this key to manage them)"
echo "    demo key: $KEY"
echo "──────────────────────────────────────────────"

# ── Optional cleanup ──────────────────────────────────────────────────
if [[ "$CLEANUP" == "1" ]]; then
  echo
  echo "[cleanup] removing demo data..."
  curl -s -o /dev/null -X DELETE "$BASE/api/braindump/$PRIV_ID" -H "Authorization: Bearer $KEY"
  curl -s -o /dev/null -X DELETE "$BASE/api/braindump/$TEAM_ID" -H "Authorization: Bearer $KEY"
  [[ -n "$KEY_ID" ]] && curl -s -o /dev/null -b "$COOKIES" -X POST "$BASE/api/keys/$KEY_ID/revoke"
  echo "[cleanup] demo entries deleted and key revoked."
fi

exit $([[ "$fail" == "0" ]] && echo 0 || echo 1)
