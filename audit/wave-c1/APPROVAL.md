# Wave C1 — protected-file approval record (P1 only)

**Date:** 2026-10-25 · **Approver:** repository owner (GokturkCan), by explicit instruction to the agent in session (~05:41 +03).
This record was written by the agent from that instruction; it is not a cryptographic signature.

**Scope: exactly the artifact below, nothing else.**

| Artifact | SHA-256 |
|---|---|
| `protected-packet/P1-inert-staging.patch` (P1 inert protected integration) | `f4cb17fae7f9ac136e0ba065087cf802e5d8c1e6f8d680701988ab71756e0943` |
| `protected-packet/P1-resulting-protected-manifest.json` (expected manifest after refresh, 79 entries) | `c95b89b4b173801c925bb6ac4dec6b35affd1bda73d26f74b9b15371a7cee02e` |

Base: `main` 56a1c6e plus approved D1 staging. The packet README is `protected-packet/README.md`.

**Approved:** D2 / P1 inert protected integration only · D10 isolation-harness *preparation* strictly scoped to Wave C1 (documents/profile only, no untrusted code) · D11 offline-first pinned-lockfile dependency policy (document) · D13 read-only verification that the independent reviewer differs from the author.

**Explicitly NOT approved:** P2 Taste activation (`protected-packet/P2-activation.patch` stays unapplied) · any global skill installation or host configuration change · installing Docker, Kubernetes, Redis or additional skill packs · running new LLM benchmark arms before isolation is verified · commit, push, PR or merge · any further protected-policy change without a separate diff.

**Constraints on this application:** the Taste files stay dormant (`adoption: benchmark`, lock status `dormant`, no `skills/` copy). Untracked `audit/run3.6/`, `scripts/r36/` and `docs/run3.6-external-review.md` belong to another session and must not be modified or included.

---

## Addendum — P1b (D15), 2026-10-25 (~06:01 +03)

**Approved by the repository owner, by explicit instruction in session:** apply the reviewed P1b security patch only.

| Artifact | SHA-256 |
|---|---|
| `protected-packet/P1b-skill-delivery-hardening.patch` | `0612f50add4433375b6022a1a80254ce18a5016bf033122616c591fc925f42db` |
| `protected-packet/P1b-resulting-protected-manifest.json` (79 entries) | `c73a2128a2473e18bd777f038b7adb190f31c17f2105979a8be59a77430db624` |

**Not authorised:** P2 activation, scope expansion, touching other sessions' files, commit, push. Taste stays dormant.
