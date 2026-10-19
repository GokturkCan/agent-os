# Compute-node contract (R3.3, Mac side)

Status: **contract + mock-tested only.** No node is connected, no network client exists, nothing was installed
or benchmarked. The Mac runs normally with the MSI powered off (default: MSI `compute.enabled: false`).

Hermes remains the single orchestrator. Mac/Hermes owns intent, eligibility, data sensitivity, authorization,
approval, global routing, cloud escalation and durable audit/task state. A node (the MSI) may only report
resources, accept or reject an **authorized** job, queue it, load/unload a runtime, run the approved offering and
return a result. It cannot approve, escalate private data, change policy, activate a model or pick a different
capability: a response naming a different node/offering/capability/model revision is `INVALID_RESPONSE`.

## Where things live (no duplicate authorities)

| Concern | Authority | Notes |
|---|---|---|
| Node identity, role, reachability, declared resources | `config/resources.yaml` (existing) | additive `nodes.<n>.compute` block: `enabled` (false), `endpoint_ref`, `auth_ref`, `declared_resources`. Refs are symbolic: no URL/IP/`@`; `auth_ref` is `env:NAME` or `keychain:NAME`. |
| Capability types, offerings, **authorizations** | `config/compute.yaml` (new, **protected**) | offerings `{}` and authorizations `[]` by default |
| Worker/tool CAN registry | `config/capability_registry.yaml` (existing, untouched) | different concern: harness tools, not node-hosted model services |
| Logic | `agentos/compute.py` (registry, ladder, validation), `agentos/compute_jobs.py` (job/error/state contract) | validated by `agentos validate` |

## The ladder (never inferred from one another)

`configured` (declared in compute.yaml) → `installed` (node advertises it at the pinned revision; discovered,
untrusted) → `healthy` (node and offering report healthy now) → `benchmarked` (state + evidence files, protected
config) → `authorized` (protected `authorizations` entry: exact revision, `max_data_class`, human `approval_ref`;
requires benchmarked) → **active** (all of the above + node enabled + node reachable). A node's advertisement can
only make an offering less eligible. A different revision is a different, unauthorized model.

## Job contract (`compute_jobs.py`)

Request: `job_id`, `idempotency_key`, `capability`, `offering`, `approved_node`, `operation`, `inputs`
(artifact refs `sha256:`/`artifact:`/`secondbrain:`, never URLs), `params` (size-capped), `deadline_seconds`
(≤3600), `resources`, `data_class`, `audit` (task_id required). Only the non-policy part is sent (`payload()`).
States: `queued → running → completed | failed | cancelled`; terminal is final; a node finishing between
observations is recorded as queued→running→completed; regressions/skips are `INVALID_RESPONSE`.
Result: status, structured `result` (completed only), `usage`, `error{code,message,retryable}`, `provenance`.
Errors: `NODE_UNAVAILABLE CAPABILITY_UNAVAILABLE NOT_AUTHORIZED RESOURCE_BUSY RESOURCE_EXHAUSTED TIMEOUT
BACKEND_FAILURE INVALID_RESPONSE CANCELLED DUPLICATE_REQUEST`. Operational failures are returned as `JobResult`
(never raised, never `ok`); only a malformed request raises `RequestInvalid`.
Idempotency: same key + same request → original result, `replayed=True`, nothing re-sent; same key + different
request → `DUPLICATE_REQUEST`. A request refused before anything was sent (policy, offline, disabled) does not
consume its key.

## R3.4 handoff (separate MSI workstream)

Minimum node API (private authenticated transport; JSON; bearer token from `auth_ref`; bind to a private/LAN/VPN
interface only, never public):

| Call | Purpose |
|---|---|
| `GET /health` | `{"ok": bool}` |
| `GET /capabilities` | `{"offerings": {"<offering_id>": {"revision": "<pinned>", "healthy": bool}}}` (advisory only) |
| `GET /resources` | free VRAM/RAM, loaded runtime, queue depth (advisory; Mac may use it for busy/exhausted hints) |
| `POST /v1/jobs` | body = `JobRequest.payload()`; returns a response per `parse_response` (unknown fields rejected) |
| `GET /v1/jobs/{id}` | current state, same shape |
| `POST /v1/jobs/{id}/cancel` | best-effort; Mac also cancels on deadline or invalid response; node returns `cancelled` |

Responses must carry `v:1, job_id, status, node, offering, capability, provenance{model_id, model_revision,
runtime}`, `usage`, and `result` (completed) or `error{code,message}` (failed). The node should itself enforce
idempotency on `idempotency_key` and reject jobs for offerings it was not told to serve.
Wrapping FreeToken/ExLlamaV3 (OpenAI-compatible): a thin node-side adapter maps `llm.chat` jobs onto the existing
`/v1/chat/completions` endpoint of the running runtime and translates the reply/usage into the job response; the
inference runtimes are not modified. The Mac never calls those endpoints directly.

First vertical slice: User → Hermes → policy (`compute.evaluate`, authorization) → Mac `NodeClient` → MSI Qwen
inference → structured `JobResult` → Mac audit. SecondBrain writes stay under the existing permission rules.

R3.4 dependencies (not done here): the real `NodeClient` over the private transport; the node-side service;
resolving `endpoint_ref`/`auth_ref` (ssh alias or env/keychain); installing and benchmarking a model so that an
offering can be `benchmarked` with evidence; a **human** adding the offering and authorization to
`config/compute.yaml`; routing integration that asks `compute.evaluate` (Hermes decides, node never routes);
durable audit (events/telemetry records of each job and replay ledger persistence); health integration for
node-level compute status.
