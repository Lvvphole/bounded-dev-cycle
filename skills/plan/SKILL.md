---
name: plan
description: >
  Turn a completed Scout handoff into the smallest sufficient PLAN_READY artifact for the
  Build Agent. Use when the user invokes /plan, supplies a Scout artifact, or asks to plan
  and sequence implementation before Build. Verify repository truth, authority, atomic
  obligations, dependencies, vertical slices, and executable evaluation gates. Do not
  implement or replace the Scout-selected path.
metadata:
  version: "2.1.0"
---

# Plan

Produce one implementation plan that Build Agent can execute without redesign or scope inference.
Workflow: `Scout -> Plan -> Build Agent -> completion authority`.
`PLAN_READY` means ready for human review and Build admission. It is not PASS.

## Boundaries

- Do not write production code, tests, configuration, schemas, commits, branches, or pull requests.
- Do not load or depend on the `engineering-rules` skill.
- Resolve `build-agent` before producing `PLAN_READY`.
- Use Build Agent's current PLAN_READY contract and Build manifest as the downstream interface.
- If Build Agent or its handoff contract cannot be resolved, return `PLAN_BLOCKED`.
- Do not self-approve the plan or declare implementation complete.

## Required Scout handoff

Require: goal, observable Definition of Done, authorized scope, non-goals, selected next path, and repository evidence references.
If goal, Definition of Done, scope, or selected path is missing, return `PLAN_BLOCKED` and name it.
If repository evidence invalidates a frozen field, return to Scout.
Do not substitute another path.

Freeze the outcome contract: goal, Definition of Done, scope, non-goals, Scout-selected path, and explicit authority boundaries.
Keep repository beliefs falsifiable: locations, implementation state, tests, CI behavior, assumptions, risks, and governance summaries.
Verify each belief before relying on it.

## Procedure

### 0. Resolve Build Agent

Resolve `build-agent`.
Read its current `references/plan-ready-contract.md` and `references/build-manifest.md`.
Resolve the bundled `scripts/source-binding.py`; it defines the only valid source-state projection.
Read other Build Agent references only when needed for a valid handoff.
Record its identity when the runtime exposes one.
Do not use a remembered schema.

### 1. Freeze the Scout contract

Record the exact frozen fields and the repository beliefs to verify.
Do not edit the goal to fit the repository.

### 2. Read repository authority

Read applicable repository instructions, specifications, ADRs, contracts, security policy, and verification policy from disk.
Apply repository precedence rules when they exist.
Treat CI as evidence unless repository authority makes it normative.
If authority conflicts and precedence does not resolve it, return `PLAN_BLOCKED` and cite both sides.

### 3. Establish repository truth

Inspect only areas needed for the selected path.
Record revision, relevant structure, implementation, tests, interfaces, CI, and working-tree state.
Verify inherited claims with `path:lines` or command output.
Record corrections without changing the frozen outcome.

Run a command only to resolve a blocking planning unknown.
First inspect its invocation path enough to establish no protected side effect.
Do not run commands for confidence or broad exploration.

### 4. Classify protected actions

For each protected action Build may need, record `AUTHORIZED`, `APPROVAL_GATED`, or `UNAUTHORIZED`.
For an approval gate, name the owner and gate boundary.
Model distinct operations separately.
Implementation authority does not imply commit, push, merge, deployment, migration, credential, or external-service authority.
For an Open PR outcome, model commit, task-branch push, PR creation, and merge separately.

### 5. Derive atomic obligations

Split every Definition-of-Done item into independently observable obligations with stable IDs.
For each obligation record behavior status (`GAP`, `PARTIAL`, `SATISFIED`), verification status (`GAP`, `PARTIAL`, `COVERED`), evidence, acceptance criterion, and meaningful oracle.

Use the status pair to select work:
- `SATISFIED + COVERED`: preserve.
- `SATISFIED + GAP/PARTIAL`: verification-only work.
- `GAP/PARTIAL behavior`: implement only the measured remainder and its verification.

### 6. Build the dependency graph

Map increment dependencies explicitly.
Reject cycles.
Order execution bottom-up.
Do not invent a shared foundation unless a declared dependency requires it.

### 7. Select the smallest admissible design

Generate alternatives only for material, hard-to-reverse, or boundary-shaping decisions.
Reject alternatives that violate the frozen contract or repository authority.
Among admissible alternatives, prefer the smallest sufficient change, fewer irreversible decisions, simpler dependencies, and stronger information hiding unless governing priorities say otherwise.
Do not add speculative features, flexibility, configurability, dependencies, or abstractions.
If selection needs an invented priority, return `PLAN_BLOCKED`.

### 8. Define required contracts and evaluation

Specify only interfaces, schemas, state transitions, ownership rules, and failure behavior required by the selected design.
Name preserved and changed brownfield contracts.
Every obligation needs an objective acceptance path and an oracle that can detect violation.
For a reproducible defect, plan failing regression evidence before the fix.
For new behavior, plan a missing-behavior signal before production change.
For refactoring, plan behavior evidence before and after.
For a boundary change, verify both sides.
Use the verifier class and protocol required by Build Agent.
Select explicit repair and timeout budgets when commands can run.
Do not copy Build Agent example budgets as defaults.

### 9. Slice vertically

Default to complete vertical behavior slices.
Each implementation increment closes one testable path across all required layers.
Use verification-only increments for evidence gaps.
Use a horizontal prerequisite only when it is a real dependency with a valid, verifiable intermediate state.
Each increment must satisfy the current Build Agent contract and declare at most five files.
If no valid five-file split exists, return `PLAN_BLOCKED`.

### 10. Protect task-list state

Determine the task-list target from repository authority.
Use Build Agent's default only when repository authority does not prescribe a target.
Require the target to be a repository-relative path without `..`.
Inspect the target and preserve unrelated or incomplete work byte-for-byte.
Provide the exact increment entries Build must record before implementation.
If safe recording is impossible, return `PLAN_BLOCKED` unless the human explicitly authorizes the overwrite.

### 11. Define checkpoints, recovery, and publication

Set a checkpoint after every increment and between major phases.
Define the expected repository state before the next increment.
For stateful work, define whole-increment recovery and its oracle.
If the frozen outcome requires an Open PR, populate Build Agent's publication contract with exact branch, base, commit scope, commit message, PR title, PR body, and authority states.
Require every commit path to be repository-relative and inside the union of declared increment files.
Always declare `merge pull request` as `UNAUTHORIZED`; Plan cannot grant merge authority.

### 12. Validate the handoff

Before `PLAN_READY`, confirm:
- every task has acceptance criteria and verification;
- dependencies are explicit, acyclic, and ordered;
- increments are vertical or justified verification-only/prerequisite work;
- no increment exceeds five files;
- checkpoints exist;
- task-list target, exact entries, and preservation evidence exist;
- no incomplete plan is overwritten;
- every protected action has an authority state;
- every executable verifier has a meaningful oracle, class, and required budgets;
- stateful work has recovery;
- every planned changed line traces to an obligation;
- no blocking unknown remains;
- the Build manifest conforms to the resolved Build Agent contract.

Any failure returns `PLAN_BLOCKED`.

### 13. Write one plan artifact

Use the repository-prescribed planning path.
If occupied by unrelated work, do not overwrite it.
When no path is prescribed, derive a collision-free path from the goal.
Require the chosen plan artifact path to be repository-relative and without `..`.
Compute the source binding by invoking Build Agent's exact `scripts/source-binding.py` with that path excluded.
Do not calculate or describe the projection independently.
Use `references/plan-template.md`.
Include exactly one `## Build manifest` using the current Build Agent schema.

The first non-empty line must be `PLAN_READY` or `PLAN_BLOCKED`.
For `PLAN_READY`, write final bytes first, then compute SHA-256.
Do not put that final artifact SHA-256 inside the artifact.
Return the artifact path and SHA-256 separately so the human can approve the exact identity before Build starts.

## Dispositions

`PLAN_READY`: ready for human review and Build Agent admission.
`PLAN_BLOCKED`: a named condition prevents a safe or complete plan; include evidence and resolution owner.
Return to Scout: evidence invalidates a frozen Scout field.
