# Capability rollout — protected-file approval record

**Date:** 2026-10-25 · **Approver:** repository owner (GokturkCan), by explicit instruction to the agent in session (~01:18 +03).
This record was written by the agent from that instruction; it is not a cryptographic signature. The owner can add an independent
record (for example a PR comment) when the PR exists.

**Scope: exactly the artifacts below, nothing else.**

| Artifact | SHA-256 |
|---|---|
| `capability-rollout-protected-packet.diff` (Protected Packet Revision 2) | `4394aca527d8899ff58938f2b3fa58ba34d3075310d5cfe2806daf10988ffc5b` |
| `capability-rollout-companion-code.diff` (unprotected companion code) | `0345f1dfd23226d13154a53b95c5d4cd7dd0dc3b2689526e85e1782cc704acab` |

Machine-readable delta (old/new file hashes, decisions): `capability-rollout-protected-delta.json`. Review rationale and evidence:
`capability-rollout-protected-packet.md`. Base: `main` a2c0897. The applied files were verified byte-identical to the reviewed copy.

**Decisions:** D1 apply exactly the packet and companion code · D2 `agentos/workers.py` GitHub credential isolation · D3 `security` CLI deny for
dispatched Claude workers only · D4 GitHub-dependent tasks fail closed (`integration-undeliverable`, human handoff, no `gh-cli` fallback; interactive
GitHub MCP stays healthy) · D5 `rea` stays `adopted`; frozen Open-Jev / FastGate / SystemOne data and decisions untouched · D6 this record and a
manifest refresh via the established workflow · D7 remove the one stale Codex temp-directory trust entry the agent's test created.

**Not authorised by this record:** commit, push, PR creation, merge, Wave C1, Run 4, new infrastructure, any later protected change.

**Run 3 history preserved:** the earlier approval is the PR #7 comment
https://github.com/GokturkCan/agent-os/pull/7#issuecomment-6295350672 (2026-10-20), scoped to commit `d77d6b0`. It is **not** authorisation for
this packet, and the historical Run 3 documents keep their original wording.

**Known limitations (also in the packet):** command-text deny patterns are best-effort, not a sandbox; `gh auth token` can still fall back to the
OS keyring (an exit code was observed once, no credential was read); a Bash-enabled worker is not a hard secrets boundary; GitHub tasks are not
dispatched to workers until a launcher can deliver HTTP + `headersHelper` servers.
