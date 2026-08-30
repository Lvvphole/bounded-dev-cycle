# Bounded Dev Cycle

A skill-only OpenAI plugin that packages three development skills and one verified engineering dependency into one installable repository workflow:

1. `scout-agent` — strict read-only repository reconnaissance that returns one evidence-grounded next path.
2. `plan` — transforms the completed Scout handoff into one bounded `PLAN_READY` artifact.
3. `build-agent` — executes only the exact human-approved `PLAN_READY` artifact with its declared verification and authority gates.
4. `engineering-rules` — provides the canonical engineering rules and deterministic `scripts/check.py` gate required by Build.

The plugin does not include an MCP server. It packages the workflow skills and engineering dependency under `skills/` and exposes them through the required `.codex-plugin/plugin.json` manifest.

## Workflow boundary

The intended cycle is:

```text
scout-agent (read-only)
    ↓ completed Scout handoff
plan (exactly once)
    ↓ PLAN_READY + exact SHA-256 identity
human review and approval of that exact plan identity
    ↓
build-agent (exactly once)
    ↓
BUILD_READY | BUILD_HALTED | BUILD_REFUSED
```

The approval boundary is deliberate. The supplied Plan and Build contracts require a human to approve the exact `PLAN_READY` identity before Build starts, so this package does not weaken or bypass that gate.

`build-agent` requires the current authoritative `engineering-rules` dependency before code analysis or mutation. This repository vendors the accepted successor bundle under `skills/engineering-rules/`. Replace that bundle only from an explicitly approved source with recorded immutable identities.

## Repository structure

```text
.
├── .agents/
│   └── plugins/
│       └── marketplace.json
├── .codex-plugin/
│   └── plugin.json
├── skills/
│   ├── scout-agent/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── plan/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── build-agent/
│   │   ├── SKILL.md
│   │   ├── agents/
│   │   ├── references/
│   │   └── scripts/
│   └── engineering-rules/
│       ├── SKILL.md
│       └── scripts/
│           └── check.py
└── README.md
```

## Add the repository marketplace

Using Codex CLI:

```bash
codex plugin marketplace add lvvphole/bounded-dev-cycle --ref main
```

Then use the ChatGPT desktop app to open the Plugins Directory, select the **Bounded Dev Cycle** marketplace, install **Bounded Dev Cycle**, and test it in a new chat.

The repository marketplace is defined at `.agents/plugins/marketplace.json`. The plugin itself lives at the repository root and is identified by `.codex-plugin/plugin.json`.

## Suggested invocation

```text
Run one bounded Scout → Plan → Build repository cycle.
Invoke scout-agent first and keep it read-only.
Invoke plan exactly once using the completed Scout handoff.
Stop for human review and approval of the exact PLAN_READY identity.
Then invoke build-agent exactly once using only that approved PLAN_READY artifact.
Stop on any blocked or failed gate.
```

## Package integrity

The contents under `skills/scout-agent`, `skills/plan`, and `skills/build-agent` remain copied directly from their supplied `.skill` archives. The `skills/engineering-rules` bundle is copied byte-for-byte from the approved successor artifact. Plugin packaging adds the manifest, marketplace metadata, and this README; it does not rewrite the supplied or approved skill contracts.
