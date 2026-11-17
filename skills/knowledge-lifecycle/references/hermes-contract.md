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