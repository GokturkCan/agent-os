#!/bin/bash
# Wave C1 isolation canaries. Non-destructive: creates ONE new uniquely named directory with known files, never deletes
# anything, never uses wildcards, touches nothing outside that directory, runs only trusted system binaries and the
# host's own node with one-liners it writes itself, and uses a loopback-only listener (no external traffic).
# usage: canary.sh <absolute base dir outside HOME and every protected path>      exit 0 = all canaries PASS
set -u
BASE="${1:-}"; [ -n "$BASE" ] && [ "${BASE#/}" != "$BASE" ] && [ -d "$BASE" ] || { echo "BLOCKED: need an existing absolute base dir"; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd -P)"; PROFILE="$HERE/wave-c1.sb"; [ -f "$PROFILE" ] || { echo "BLOCKED: profile missing"; exit 2; }
BASE="$(cd "$BASE" && pwd -P)"; HOME_R="$(cd "$HOME" && pwd -P)"
for P in "$HOME_R" "$HOME_R/agent-stack" "$HOME_R/SecondBrain" "$HOME_R/.claude" "$HOME_R/.hermes" "$HOME_R/.codex" "$HOME_R/.config"; do
  case "$BASE/" in "$P"/*) echo "BLOCKED: $BASE is inside $P"; exit 2;; esac
done
D="$(mktemp -d "$BASE/c1-canary-XXXXXXXX")" || { echo "BLOCKED: mktemp failed"; exit 2; }; D="$(cd "$D" && pwd -P)"
mkdir "$D/work" "$D/tmp" "$D/fakehome" "$D/fakehome/.ssh" "$D/srv"
echo CANARY-SSH-KEY > "$D/fakehome/.ssh/id_fake"; echo outside-original > "$D/outside.txt"; echo SERVED > "$D/srv/index.html"
fail=0; ok(){ printf 'PASS  %s\n' "$1"; }; bad(){ printf 'FAIL  %s\n' "$1"; fail=1; }
sbx(){ /usr/bin/sandbox-exec -D WORK="$D/work" -D TMP="$D/tmp" -f "$PROFILE" /usr/bin/env -i PATH=/usr/bin:/bin HOME="$D/work" TMPDIR="$D/tmp/" "$@"; }
echo "canary dir: $D"
[ "$(sbx /bin/echo ok 2>&1)" = ok ] && ok "exec of an allowed binary" || bad "exec of an allowed binary"
sbx /bin/sh -c "echo x > '$D/work/a.txt'" >/dev/null 2>&1; [ "$(cat "$D/work/a.txt" 2>/dev/null)" = x ] && ok "write inside WORK" || bad "write inside WORK"
sbx /bin/sh -c "echo x > '$D/tmp/b.txt'" >/dev/null 2>&1; [ "$(cat "$D/tmp/b.txt" 2>/dev/null)" = x ] && ok "write inside TMP" || bad "write inside TMP"
sbx /bin/sh -c "echo HACKED > '$D/outside.txt'" >/dev/null 2>&1; [ "$(cat "$D/outside.txt")" = outside-original ] && ok "overwrite outside is denied (host-verified)" || bad "overwrite outside"
sbx /bin/sh -c "echo x > '$D/fakehome/new.txt'" >/dev/null 2>&1; [ ! -e "$D/fakehome/new.txt" ] && ok "create outside is denied (host-verified)" || bad "create outside"
out="$(sbx /bin/cat "$D/fakehome/.ssh/id_fake" 2>&1)"; case "$out" in *CANARY*) bad "read of fake ~/.ssh canary";; *) ok "read of fake ~/.ssh canary denied";; esac
out="$(sbx /bin/cat "$D/outside.txt" 2>&1)"; case "$out" in *outside-original*) bad "read outside file";; *) ok "read of an outside file denied";; esac
export CANARY_TOKEN=should-not-leak
[ "$(sbx /bin/sh -c 'echo ${CANARY_TOKEN:-unset}')" = unset ] && ok "environment scrubbed by env -i allowlist" || bad "environment leak"
PORT="$(/usr/bin/python3 -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")"
/usr/bin/python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$D/srv" > "$D/srv.log" 2>&1 & LPID=$!; sleep 1
[ "$(/usr/bin/curl -s -m 3 "http://127.0.0.1:$PORT/")" = SERVED ] && ok "positive control: listener reachable from OUTSIDE the sandbox" || bad "positive control"
sbx /usr/bin/curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/" >/dev/null 2>&1; [ $? -ne 0 ] && ok "loopback connection from inside denied" || bad "loopback connection allowed"
[ "$(grep -c 'GET /' "$D/srv.log")" = 1 ] && ok "listener saw exactly the 1 outside request" || bad "listener request count"
NODE="$(command -v node || true)"
if [ -n "$NODE" ]; then
  cat > "$D/work/probe.js" <<JS
const fs=require('fs'),net=require('net');const o={};
try{fs.writeFileSync('$D/work/n.txt','n');o.wi='ok'}catch(e){o.wi=e.code}
try{fs.writeFileSync('$D/outside.txt','HACKED');o.wo='LEAK'}catch(e){o.wo=e.code}
try{fs.readFileSync('$D/fakehome/.ssh/id_fake');o.rc='LEAK'}catch(e){o.rc=e.code}
o.env=process.env.CANARY_TOKEN||'unset';
const s=net.connect($PORT,'127.0.0.1');s.on('connect',()=>{o.net='LEAK';s.destroy();d()});s.on('error',e=>{o.net=e.code;d()});
function d(){console.log(JSON.stringify(o));process.exit(0)} setTimeout(d,3000);
JS
  res="$(sbx "$NODE" "$D/work/probe.js" 2>&1 | tail -1)"
  [ "$res" = '{"wi":"ok","wo":"EPERM","rc":"EPERM","env":"unset","net":"EPERM"}' ] && ok "node: write inside ok; outside write/read, env and network all denied" || bad "node probe: $res"
else echo "SKIP  node not found"; fi
kill "$LPID" 2>/dev/null; wait "$LPID" 2>/dev/null; unset CANARY_TOKEN
[ "$(cat "$D/outside.txt")" = outside-original ] && ok "final host check: outside file unchanged" || bad "final host check"
echo "$([ $fail = 0 ] && echo 'ALL CANARIES PASS' || echo 'CANARY FAILURES')  (directory left in place, nothing deleted: $D)"
exit $fail
