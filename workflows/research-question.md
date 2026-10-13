# Workflow: bounded research question (Phase 10 placeholder interface)

Status: **DESIGN-ONLY interface.** No research subsystem (OpenResearch, AIRA,
AutoResearch) is installed. This file fixes how one will plug in so none can
become a second orchestrator or a second memory.

```
Hermes (research director: goal, budget, risk, permissions)
  -> route {type: research}                    config/routing.yaml task_classes.research
  -> TaskStore.create(..., task_class=research, budgets=...)   same LoopContract + budgets
  -> research workspace: ~/research-workspaces/runs/<task_id>/   (research_worker fs role)
  -> subordinate research system (adapter)     receives: question, budget, allowed tools
                                               returns: artifacts + metrics + negative results
  -> deterministic metrics / held-out eval     never modifiable by the research system
  -> independent evaluation                    evaluator != generator
  -> Hermes -> knowledge gate                  findings + failed branches as lesson/evidence
```

Adapter contract for any research subsystem (`adapters/README.md`):
input = task.yaml + workspace path; output = files in the workspace + a
`result.json` {exit_state, metrics, artifacts, negative_results}. It never
writes SecondBrain, never dispatches other workers, never holds provider keys
beyond what its capability profile grants.
