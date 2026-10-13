"""Acceptance 7 — PERMISSIONS: a restricted worker cannot silently gain
high-impact capabilities."""
import pytest

from agentos.permissions import PermissionDenied, WorkerSession, is_protected, write_grant
from agentos.workers import build_launch

HIGH_IMPACT = ["git_push", "credential_change", "permission_change", "external_publish",
               "secrets_read", "destructive_delete", "modify_judge", "modify_heldout_evals"]


def test_readonly_worker_denied_writes_and_high_impact(cfg):
    s = WorkerSession.start(cfg, "claude_code", "readonly")
    assert s.check("fs_read")
    for cap in ["fs_write_worktree", "shell", "git_commit_local", *HIGH_IMPACT]:
        assert not s.check(cap), cap
    assert all(a["reason"] for a in s.audit)              # every decision is auditable


def test_coder_still_cannot_hold_never_grantable(cfg):
    s = WorkerSession.start(cfg, "codex", "coder")
    for cap in HIGH_IMPACT:
        with pytest.raises(PermissionDenied, match="never_grantable"):
            s.require(cap)


def test_escalation_needs_operator_grant_with_human_approval(cfg, tmp_path):
    s = WorkerSession.start(cfg, "claude_code", "readonly")
    with pytest.raises(PermissionDenied):
        s.request_escalation("coder", None)
    forged = {"issued_by": "claude_code", "worker": "claude_code", "profile": "coder",
              "human_approval_ref": "trust me"}
    with pytest.raises(PermissionDenied):
        s.request_escalation("coder", forged)             # self-issued grant rejected
    grant = write_grant("claude_code", "coder", "human:ticket-42", directory=tmp_path)
    s2 = s.request_escalation("coder", grant)
    assert s2.check("fs_write_worktree")


def test_profile_outside_worker_allowlist_refused(cfg):
    with pytest.raises(PermissionDenied):
        WorkerSession.start(cfg, "opencode", "reviewer")
    with pytest.raises(PermissionDenied):                 # canonical-write approval is human-only
        WorkerSession.start(cfg, "claude_code", "knowledge_reviewer")


def test_launch_commands_encode_restrictions(cfg, tmp_path):
    ro = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "readonly"), "p", tmp_path)
    allowed = ro["argv"][ro["argv"].index("--allowedTools") + 1]
    denied = ro["argv"][ro["argv"].index("--disallowedTools") + 1]
    assert "Edit" not in allowed.split(",") and "Write" not in allowed.split(",")
    assert "Edit" in denied and "Bash(git push:*)" in denied
    assert ro["argv"][ro["argv"].index("--permission-mode") + 1] == "default"
    cx = build_launch(cfg, WorkerSession.start(cfg, "codex", "readonly"), "p", tmp_path)
    assert cx["argv"][cx["argv"].index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in cx["argv"]


def test_candidate_workers_cannot_launch(cfg, tmp_path):
    with pytest.raises((PermissionDenied, KeyError)):
        build_launch(cfg, WorkerSession.start(cfg, "local_qwen"), "p", tmp_path)


def test_policy_files_are_protected():
    for p in ["config/permissions.yaml", "config/capabilities.yaml", "config/promotion.yaml",
              "evals/test_a7_permissions.py", "CLAUDE.md", "agentos/permissions.py",
              "config/workers.yaml", "config/mcp.yaml", "config/capability_registry.yaml",
              "agentos/workers.py", "agentos/githooks/pre-push"]:
        assert is_protected(p), p
    assert not is_protected("config/routing.yaml") and not is_protected("agentos/router.py")
