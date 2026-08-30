# Context Routing

## How to use this file
Read this file to determine which context to load for a task.
Load only the files listed under `Context` for the current task.
Stop when the task's declared output and verification contract are satisfied.

## Task: plugin-packaging
### Context
- Reference: `README.md`, `AGENTS.md`, `.governance/security.md`, `.governance/testing.md`
- Working: `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`
- Scope: plugin manifests, marketplace metadata, root packaging documentation
### Process
- Preserve the documented Scout → Plan → human approval → Build boundary.
- Change only packaging metadata or documentation required by the task.
- Do not rewrite supplied skill contracts.
### Outputs
- Produce the minimum required manifest, marketplace, or README changes.
### Verification
- Run `git diff --check`.
- Run `python -m json.tool .codex-plugin/plugin.json` for plugin-manifest changes.
- Run `python -m json.tool .agents/plugins/marketplace.json` for marketplace changes.

## Task: skill-bundle-update
### Context
- Reference: `README.md`, `AGENTS.md`, `.governance/security.md`, `.governance/testing.md`
- Working: only the explicitly authorized `skills/<skill-name>/` bundle
- Scope: one supplied skill bundle at a time
### Process
- Require an explicit authoritative source for the replacement bundle.
- Require `git status --porcelain` to be empty before the first mutation; otherwise stop.
- Record the immutable pre-task commit SHA as `BASE_SHA` before the first mutation; do not recompute it during the task.
- Preserve bundle identity and do not opportunistically edit neighboring skills.
- Do not add root governance files inside a supplied skill bundle.
- Stop if provenance, approval, or required external dependencies cannot be verified.
### Outputs
- Replace only the authorized bundle content and record what source was used.
### Verification
- Run `git diff --check "$BASE_SHA" --`.
- Run `git diff --name-only "$BASE_SHA" --` to list all tracked task changes, including committed, staged, and unstaged changes.
- Run `git ls-files --others --exclude-standard` to list untracked task files.
- Validate the union of both path lists; every path must be inside the single authorized `skills/<skill-name>/` bundle.
- Fail if any root path, neighboring bundle path, or other out-of-scope path appears.
- Confirm each required `SKILL.md` remains present.

## Task: bug-fix
### Context
- Reference: `README.md`, `AGENTS.md`, `.governance/security.md`, `.governance/testing.md`
- Working: only the explicitly authorized defect and directly affected verification files
- Scope: paths authorized by the task or approved plan; no adjacent cleanup
### Process
- Preserve a reproducible failing case and relevant environment evidence before the first repair mutation.
- Separate the observed failure from the suspected cause and test a falsifiable cause hypothesis.
- Establish a meaningful failing oracle before repairing reproducible faulty behavior.
- `BUGFIX-REMOVE-FIRST`: Before adding code or configuration, determine whether removing incorrect, redundant, conflicting, or unnecessary implementation restores the contract; prefer removal or simplification when sufficient.
- `BUGFIX-NO-INVENTED-FILES`: Do not create a new file unless the task or approved plan explicitly authorizes that exact path and purpose; do not invent helper, wrapper, abstraction, configuration, documentation, or test files.
- Make only the minimum repair supported by the evidence.
- Require new evidence before another repair mutation; stop when further mutation would be speculative or outside authority.
### Outputs
- Produce the minimum repair and the evidence required to verify the defect transition.
### Verification
- Require the original targeted oracle to fail on the bound faulty baseline and pass on the repaired candidate.
- Run the affected regression verification required by `.governance/testing.md`.
- Validate the complete tracked-plus-untracked change set against authorized scope.
- Stop and report `BLOCKED` if required verification cannot be performed or valid verification would need to be weakened.

## Task: governance-change
### Context
- Reference: `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `.governance/`
- Working: only the governance files named in the approved task
- Scope: root governance and `.governance/`
### Process
- Keep operational rules in `AGENTS.md`; keep routing in `CONTEXT.md`.
- Keep `CLAUDE.md` orientation-only.
- Preserve repository-specific authority boundaries from `README.md`.
- Avoid duplicating extended policy text across files.
### Outputs
- Update only the governance files required by the approved change.
### Verification
- Run `git diff --check`.
- Confirm `AGENTS.md` is at most 100 lines.
- Confirm `CLAUDE.md` is at most 30 lines.
- Confirm every referenced governance path exists.

## Task: documentation
### Context
- Reference: `README.md`, `AGENTS.md`, `.governance/style.md`
- Working: the explicitly named Markdown file
- Scope: documentation only
### Process
- Preserve canonical workflow names and approval semantics.
- Do not claim files, commands, tests, integrations, or guarantees that are not present.
### Outputs
- Produce the smallest accurate documentation change.
### Verification
- Run `git diff --check`.
- Compare changed claims against current repository files.

## Task: security-review
### Context
- Reference: `AGENTS.md`, `.governance/security.md`, `.governance/risk-register.md`
- Working: read-only unless a separate remediation task is approved
- Scope: repository authority, manifests, skill provenance, secrets, and workflow gates
### Process
- Identify authority escalation, provenance, prompt-injection, secret, isolation, and approval-bypass risks.
- Separate verified evidence from inference.
### Outputs
- Produce findings with affected paths, evidence, impact, and bounded remediation.
### Verification
- Confirm every finding cites current repository evidence.
- Do not mutate the repository during review-only work.

## Assumptions
- This repository has no general application build or test suite yet.
- The declared plugin and skill paths in `README.md` are intended future repository paths.
- Supplied skill bundles are integrity-sensitive package content rather than monorepo subprojects.
