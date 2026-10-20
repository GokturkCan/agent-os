# Module changes and evidence lineage

Inherited files under modules/ remain byte-identical (see inherited-evidence-sha256.json).
The interrupted session's exact earlier source snapshots are unavailable; statements
about its earlier implementation changes are inferred from current code and retained
run1 outcomes, not fabricated patch history.

- ContextGate first run: 4/35 essential facts lost, 55.94% estimated token reduction.
  Current inherited implementation retains tail lines and full protected lines at
  the head boundary; inherited subsequent run: 0/35 lost, 50.71% reduction.
- Laya pruner first run: 2/27 essential lines lost; inherited subsequent run: 0/27,
  47.34% reduction. Current inherited code pins first/last unprotected chunks.
- Recovery changes: content store uses bytes, preserving CRLF exactly and verifies
  SHA-256 on retrieval. Tests include tampered content.
- Pruner shares ContextGate's security/path protections and preserves protected
  text before carriage-return redraws; every changed view has an original hash.
  On this suite deterministic estimated savings fall from 63.85% to 46.06%, with
  zero essential-line loss. Safety takes precedence over maximizing savings.
- WakeGate now recognizes approval/error text in every event kind, before model
  inference. Existing deterministic acceptance remains 0 missed, 14 unnecessary
  wakes and 4 avoided reasoning turns out of 46 events.
- Rule cache now keys exact state, resource facts, question, abstention and cost
  in addition to the preregistered fields; hashes all config YAML files. Empty
  named-human approval is rejected; restored approval provenance is checked.
  This is a caller-controlled prototype, not a cryptographic human authentication
  system. No real rule has been approved or activated by this implementation.
- Pipeline validates the inner response through system_one; per-option error
  replies and conflicting choice+abstain fail closed before interpreting scores.
- Compatibility reserves escalation IDs to prevent response-key collisions.
- Module CLI returns failure when acceptance fails, rather than always exit 0.

Token counts are ceil(chars/4) estimates, not actual tokenizer counts. Module
suites are author-written development/acceptance fixtures, not unseen production
workloads. Original recovery and safety guarantees are narrower than arbitrary
semantic retention: unprotected text may still contain useful facts. No activation.
