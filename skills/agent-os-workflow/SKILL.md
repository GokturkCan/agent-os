---
name: agent-os-workflow
description: "REQUIRED for multi-step research+implement workflows. NL → agentos workflow request only."
version: 1.0.0
---

# Agent OS — Workflow (Hermes contract)

For requests like parallel research, join, implement, verify, remember, and continue:

**Do not** invent workflow YAML, node IDs, or success without running Agent OS.

## Execute (required)

```bash
~/agent-stack-integration/bin/agentos workflow request \
  --text "USER OBJECTIVE VERBATIM" \
  --project "PROJECT NAME OR ID" \
  --repo /absolute/path/to/repo \
  --max-parallel 2
```

Valid success: `"schema": "agentos.hermes-workflow-execute.v1"`, `"status": "done"`, non-zero `checkpoint_seq`, paths under `evidence`.

## Continue / where we stopped on this graph

```bash
~/agent-stack-integration/bin/agentos workflow continue WORKFLOW_ID --project "PROJECT"
~/agent-stack-integration/bin/agentos workflow status WORKFLOW_ID
```

On blocked graphs, repair only failed nodes:

```bash
~/agent-stack-integration/bin/agentos workflow repair-node WORKFLOW_ID NODE_ID
~/agent-stack-integration/bin/agentos workflow resume WORKFLOW_ID
```

## Plan-only preview

```bash
~/agent-stack-integration/bin/agentos workflow plan \
  --text "..." --project "..." --repo /absolute/repo
```

Returns `"schema": "agentos.hermes-workflow-plan.v1"` with `planned_nodes` — no execution.