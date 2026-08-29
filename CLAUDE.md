# Bounded Dev Cycle

This repository packages a bounded Scout → Plan → Build coding workflow.

## Agent instructions
Read [AGENTS.md](./AGENTS.md) for build, test, style, security, architecture, and workflow rules.

## Task routing
Read [CONTEXT.md](./CONTEXT.md) to load only the context required for the current task.

## Governance
The `.governance/` directory contains enforceable policies:
- `security.md` — tool authority, secrets, isolation, and approval gates
- `testing.md` — verification commands and completion contracts
- `style.md` — Markdown, JSON, naming, and diff-discipline rules
- `risk-register.md` — known agent and packaging risks with mitigations

## Assumptions
- Root governance controls repository work; supplied skill bundles remain self-contained.
- `README.md` is the current repository context source until additional governed artifacts exist.
