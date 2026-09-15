# Agent Stack Bootstrap

This repository is the control-plane and configuration source for my local Agent OS.

## Core Principles

- Keep the root instructions small.
- Prefer progressive disclosure over loading everything into context.
- Agent identity and model identity are separate.
- Use the narrowest applicable skill or workflow.
- Do not stack multiple overlapping planning frameworks unless explicitly needed.
- Prefer deterministic checks over LLM judgment whenever possible.
- State must live outside chat context.
- Durable knowledge belongs in `~/SecondBrain`.
- Raw sources are not canonical knowledge.
- Self-improvement must go through proposal, evaluation, review, and promotion.
- Permissions are enforced by capability boundaries, not only prompts.

## Main Paths

- Agent OS: `~/agent-stack`
- Durable knowledge: `~/SecondBrain`
- Research runtime: `~/research-workspaces`

## Context Loading

Before doing substantial work:

1. Read the relevant project state.
2. Read only the relevant knowledge from `~/SecondBrain`.
3. Use search/indexes before broad vault reads.
4. Avoid loading the entire vault unless explicitly necessary.

## Workflow Selection

- Normal task: one primary worker.
- Complex task: add one or two specialists/reviewers.
- Research task: use Research Mode only when open-ended experimentation is needed.
- Repeatable stabilized workflows should later move into deterministic automation.

## Safety

- Never expose secrets.
- Do not silently overwrite canonical knowledge.
- Do not modify judges, permissions, or critical policies without review.
- Prefer read-only access unless write access is required.
