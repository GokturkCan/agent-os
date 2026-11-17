# Hermes contract commands

These commands define success in operational state, not in chat prose.

## remember

```bash
~/agent-stack-integration/bin/agentos knowledge remember \
  --project "Agent OS" \
  --text "One concise durable sentence the user authorized."
```

Valid success JSON includes `"schema": "agentos.hermes-knowledge-capture.v1"`, `"status": "captured"`, `"verified_on_disk": true`.

## where-stopped

```bash
~/agent-stack-integration/bin/agentos knowledge where-stopped \
  --project "Agent OS" \
  --repo /Users/gokturkcan/agent-stack
```

Valid success JSON includes `"schema": "agentos.where-stopped.v1"`, `"status": "ok"`, nested `project_status` and `continuation`.

No vault writes. No fabricated proposal IDs.

## workflow (multi-step operational graph)

```bash
~/agent-stack-integration/bin/agentos workflow init demo-graph --spec fixtures/workflows/demo-graph.yaml
~/agent-stack-integration/bin/agentos workflow run demo-graph --max-parallel 2
~/agent-stack-integration/bin/agentos workflow status demo-graph
```

On node failure, repair only the failed node (completed siblings are not reset):

```bash
~/agent-stack-integration/bin/agentos workflow repair-node demo-graph research-b
~/agent-stack-integration/bin/agentos workflow resume demo-graph
```

Success is `"status": "done"` in workflow JSON with per-node `done` and checkpoint `checkpoint_seq` increasing.