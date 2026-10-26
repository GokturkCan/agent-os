#!/bin/zsh
# SECURITY NOTE: this is NOT a sandbox. `Bash(node:*)`/`Bash(python3:*)` let an arm run arbitrary code as the invoking user with the
# real $HOME and network; the deny patterns are command-text matching only (defence in depth). It was used under supervision with
# skills whose scripts had been read first. Before reuse with any unreviewed skill, run each arm in a container/VM with no home mount,
# no credentials and egress blocked (e.g. docker --network none), or narrow the allowlist to exact scripts.
# usage: run_arm.sh <task> <arm> <fixture-dir> <prompt-file> [skill-src-dir:skillname ...]
# Builds an isolated workspace, installs the listed skills as PROJECT skills (never touches ~/.claude etc.), runs claude -p.
set -u
B=/private/tmp/claude-501/-Users-gokturkcan-agent-stack/f3ecec3e-a2dd-48ef-8659-5ee3dd61580c/scratchpad/bench
task=$1; arm=$2; fx=$3; pf=$4; shift 4
ws=$B/ws/${task}__${arm}; rm -rf $ws; mkdir -p $ws/.claude/skills; cp -R $fx/. $ws/
for s in "$@"; do src=${s%%:*}; name=${s##*:}; mkdir -p $ws/.claude/skills/$name; cp -R $src/. $ws/.claude/skills/$name/; done
mkdir -p $ws/tools; cp $B/tools/shot.mjs $ws/tools/ 2>/dev/null
cd $ws && git init -q && git -c user.email=b@x -c user.name=bench add -A >/dev/null 2>&1 && git -c user.email=b@x -c user.name=bench commit -qm "initial" >/dev/null 2>&1
prompt=$(cat $pf)
start=$(date +%s)
TASTE_SKILL_HISTORY=$ws/.taste-history.json perl -e 'alarm 1500; exec @ARGV' claude -p "$prompt" --output-format stream-json --verbose \
  --setting-sources project --strict-mcp-config --no-session-persistence --permission-mode acceptEdits --max-budget-usd 3 \
  --allowedTools "Bash(node:*)" "Bash(python3:*)" "Bash(git:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(wc:*)" "Bash(grep:*)" "Bash(mkdir:*)" "Bash(head:*)" "Bash(diff:*)" \
  --disallowedTools "WebFetch" "WebSearch" "Bash(curl:*)" "Bash(wget:*)" "Bash(npm:*)" "Bash(npx:*)" "Bash(pip:*)" "Bash(pip3:*)" "Bash(gh:*)" "Bash(security:*)" "Bash(*assets.mjs*)" "Bash(open:*)" "Bash(sudo:*)" \
  > $B/out/${task}__${arm}.jsonl 2> $B/out/${task}__${arm}.err
echo "$(( $(date +%s) - start ))" > $B/out/${task}__${arm}.wall
