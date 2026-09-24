# NVIDIA NIM Provider Audit — 2026-09-23

## Connectivity

Verified:

- DNS resolution for `integrate.api.nvidia.com`: OK
- HTTPS/TLS connection: OK
- NVIDIA API authentication: OK
- `GET /v1/models`: HTTP 200

## Kimi K3

Model:

`moonshotai/kimi-k3`

Verified present in NVIDIA model catalog.

Inference tests:

1. Chat completion request:
   - timeout: 60 seconds
   - result: 0 bytes received

2. Streaming request using `Accept: text/event-stream`:
   - timeout: 90 seconds
   - result: 0 bytes received

Conclusion:

Kimi K3 is currently not reliable enough to be a production dependency.

## Control Model

Model:

`openai/gpt-oss-20b`

Using the same:

- API key
- hostname
- `/v1/chat/completions` endpoint
- streaming protocol

Result:

- HTTP/2 200
- streaming response received immediately
- NVIDIA request status: fulfilled

The model consumed the small completion budget with reasoning and terminated
with `finish_reason: length`, but the serving path itself worked correctly.

## Diagnosis

The failure is not caused by:

- local networking
- DNS
- TLS
- NVIDIA authentication
- missing NVIDIA SDK
- the generic NIM chat-completions endpoint

The observed failure is specific to the Kimi K3 serving path/backend at the
time of testing.

## Current Policy

NVIDIA NIM remains available as an experimental/opportunistic provider.

`moonshotai/kimi-k3` must not be treated as the Agent OS production primary
until it passes reliability testing.
