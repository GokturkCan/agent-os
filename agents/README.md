# agents/ — worker role contracts

Role contracts are machine-readable and live in config, not duplicated here:

- which workers exist, their status, roles and launch templates → `config/workers.yaml`
- what each worker may do (capability profiles, never-grantable list) → `config/capabilities.yaml`
- filesystem scope per role → `config/permissions.yaml`
- which worker a task class routes to → `config/routing.yaml`

Hermes is the orchestrator and is deliberately not selectable as a worker
(`workers.hermes_delegation.selectable: false`).
