# PLAN_READY admission contract

Use this contract before any repository mutation.
A missing required item stops Build.

## Required input state

- The first disposition token is exactly `PLAN_READY`.
- A trusted expected SHA-256 for the finalized plan arrives independently from the plan artifact.
- The current human has reviewed and approved this exact plan identity.
- The plan contains the machine-readable Build manifest defined in `references/build-manifest.md`.
- The plan names the completion authority.

Run `scripts/validate-plan-ready.py` before any repository write.
Use its non-zero exit status as a blocking structural result.

## Required outcome fields

The plan must contain goal, Definition of Done, authorized scope, non-goals, selected design, contracts and invariants, atomic obligations, and source-state binding.
Do not accept a compound obligation when its outcomes can fail independently.
Each obligation must have an objective acceptance path.

## Required increment fields

Each increment must contain the fields required by the current Build manifest.
Use at most five declared files in one increment.
If more files are required, return the plan for a smaller valid increment.

## Task-list admission

The Build manifest must name one task-list target and the exact entries for all increments.
Plan must provide preservation evidence for existing unrelated or incomplete content.

After admission and before the first implementation write, Build records any missing declared entries without modifying unrelated content.
If the target cannot be updated without overwriting unrelated work, stop and request explicit human direction.
Do not require the human to perform a separate task-list synchronization step.

## Verifier classes

`DETERMINISTIC` means the verifier must agree on the same unchanged candidate state.
Run the plan-declared same-state stability check before treating its result as evidence.

`DECLARED_NONDETERMINISTIC` means Plan supplies the complete protocol.
The protocol must specify trial count, acceptance criterion, candidate-state requirement, and stopping rule.
Run exactly that protocol.

A missing determinism class makes the plan invalid for Build.

## Dependency and slicing checks

Confirm that the dependency graph is acyclic.
Confirm that declared execution order is bottom-up through the graph.
Each implementation increment must close one testable vertical behavior path.
A verification-only increment can close an evidence gap without production changes.

## Source binding

Verify the exact source state used by Plan before the first repository action.
Run `python scripts/source-binding.py --repo <repo> --exclude-plan-path <source_binding.excluded_plan_path>`.
Compare all five returned fields with the manifest `source_binding` object.
The bundled script is the only canonical source-state projection for this contract.
It pins Git configuration and ignores ambient user, global, and system settings, so two sessions on the same worktree return the same binding.
It records an untracked nested repository by its worktree content under `kind: "nested-repo"`, excluding that repository's own history.
A binding failure is a stop condition, not a value to reconstruct by hand.
Verify the plan artifact identity separately from the source-state identity.
Do not treat a hash written inside the plan as independent proof of that plan's identity.

## Governance freshness

Before the first mutation, read the applicable current governance from disk.
Treat the plan's governance snapshot as historical evidence, not current authority.
If current governance invalidates the authorized execution path, stop before mutation.

## Publication admission

`publication.mode: "NONE"` authorizes no commit, push, pull request, merge, or deployment.

For `publication.mode: "OPEN_PR"`, require exact branch, base branch, commit message, commit paths, pull request title, pull request body, and protected-action states.
Commit, push, and pull request creation must each be `AUTHORIZED` before execution.
Do not infer merge authority from pull request authority.
If any required publication action is `APPROVAL_GATED`, stop at that gate after local verification and preserve the verified candidate.
