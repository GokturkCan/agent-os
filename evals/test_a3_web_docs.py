"""Acceptance 3 — WEB / DOCS (+ tool-selection family)."""
import pytest

from agentos import router
from agentos.permissions import WorkerSession
from agentos.workers import build_launch


def test_developer_docs_route_to_context7_not_browser(cfg):
    r = router.route_tool(cfg, "developer_docs")
    assert r["tool"] == "context7"
    assert not any(t in " ".join(r["trace"]) for t in ("playwright", "browser_use", "firecrawl"))


@pytest.mark.parametrize("need,expected", [
    ("github_structured", "gh_cli_readonly"),      # github MCP failing (401) -> read-only CLI
    ("deterministic_browser", "playwright"),
    ("open_ended_browser", "playwright"),          # browser-use deferred -> narrower tool
    ("file_to_markdown", "claude_obsidian_capture"),
    ("public_web_scrape", "web_fetch"),            # firecrawl not installed
    ("code_navigation", "serena"),
    ("repo_packing", "ripgrep"),                   # repomix candidate only
])
def test_tool_routing_uses_only_usable_tools(cfg, need, expected):
    assert router.route_tool(cfg, need)["tool"] == expected


def test_github_mcp_selected_once_healthy(cfg):
    r = router.route_tool(cfg, "github_structured", {"tools": {"github_mcp": "ok"}})
    assert r["tool"] == "github_mcp"


def test_coding_worker_gets_no_broad_browser_or_account_connectors(cfg, tmp_path):
    launch = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "coder"), "x", tmp_path)
    assert launch["mcp_servers"] == ["context7", "serena"]
    assert "--strict-mcp-config" in launch["argv"]         # ambient connectors excluded
    for forbidden in ("playwright", "gmail", "slack", "github"):
        assert forbidden not in launch["argv"][launch["argv"].index("--allowedTools") + 1]


def test_browser_exposed_only_when_task_requests_it(cfg, tmp_path):
    launch = build_launch(cfg, WorkerSession.start(cfg, "claude_code", "readonly"), "x", tmp_path,
                          extra_mcp=("playwright",))
    assert "playwright" not in launch["mcp_servers"]      # readonly lacks mcp_playwright grant
