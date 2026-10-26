# Wave C1 benchmark harness

Reproduces `../benchmark-results.md`. Everything here is test scaffolding, not an Agent OS capability; it is not imported by anything and lives outside `evals/`.

- `fixtures/` — starting repos per task (`debug`, `ts-impl`, `react-review`, `anim-review`, `legacy-audit`, `ui/legacy`).
- `hidden/` — hidden test suites and the planted-defect list, plus `ref/cache.ts`, the reference solution used to validate the cache suite. Never copy these into a workspace before the arm finishes.
- `prompts/` — the identical task prompts; `<task>_<arm>.txt` adds one line "Use the `<skill>` skill".
- `tools/run_arm.sh` — builds an isolated scratch repo, copies the skill into the repo's own `.claude/skills/`, runs `claude -p` with `--setting-sources project --strict-mcp-config --no-session-persistence`, denies network/installers. **Edit the hard-coded `B=` scratch path first.** In zsh write `"${DIR}:name"` (a bare `$DIR:name` is parsed as a parameter modifier and silently breaks the skill install; this invalidated three early runs).
- `tools/check_ui.mjs` — independent UI checker (Node ≥ 22, Google Chrome path hard-coded). `tools/score_*.py/.sh`, `summarize.py` — scoring.
- `results/` — checker JSON per page, the taste inspector JSON, and the final answer text of every run. `outputs/` — the five generated pages. `pinned-wdg-skill/` — the pinned Web Interface Guidelines skill used in the audit arm.
- Skill sources were shallow clones of the pins in `../capability-matrix.md`; they are not copied here (except the pinned guidelines text).

## Security limits
`run_arm.sh` is **not a sandbox**: interpreter allowlists permit arbitrary code as your user with your real `$HOME`. Only use it on skills whose scripts you have read, supervised. For anything else use a container/VM with no home mount, no credentials and no network egress.
