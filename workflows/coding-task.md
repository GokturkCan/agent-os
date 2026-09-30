# Workflow: coding task (one primary worker)

Verified end-to-end by `evals/test_a2_coding.py` (deterministic) and
`test_live_claude_worker` (live, `AGENTOS_LIVE=1`).

```
event {type: coding}
  -> agentos.router.route()            C4 chain: claude_subscription -> codex_subscription
  -> TaskStore.create(task_id, LoopContract) + accept_plan()
  -> worktree.create(repo, task_id)    branch agentos/<task_id>, never the main checkout
  -> worktree.acquire(wt, worker)      single-owner lease (git-dir, not in checkout)
  -> WorkerSession.start(worker, profile=coder)
  -> workers.build_launch() / run()    strict MCP set, allowed tools / sandbox from profile
  -> deterministic verification        e.g. pytest; record_test(), iterate(progress)
  -> [optional] independent review     reviewer worker != primary (routing.roles.reviewer)
  -> commit on task branch, release lease, Task.close(exit_state), telemetry.record()
  -> human merges (agents never merge to main or push)
  -> worktree.remove()                 refuses if leased or dirty
```

Escalation: after `no_progress`, route `background_coding_escalation`
(DeepSeek Harness on NVIDIA NIM, background only). High-risk markers route to
`human_handoff`.
