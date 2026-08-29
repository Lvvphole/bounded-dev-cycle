# Testing and Verification Policy

## Test commands
Run from the repository root as applicable:
- `git diff --check`
- `python -c "from pathlib import Path; assert Path('README.md').is_file()"`
- `python -m json.tool .codex-plugin/plugin.json`
- `python -m json.tool .agents/plugins/marketplace.json`
- `python -c "from pathlib import Path; assert all(Path(p).is_file() for p in ['skills/scout-agent/SKILL.md','skills/plan/SKILL.md','skills/build-agent/SKILL.md'])"`

For scoped mutation tasks, capture the immutable pre-task commit as `BASE_SHA` before the first mutation, then run:
- `git diff --check "$BASE_SHA" --`
- `git diff --name-only "$BASE_SHA" --`
- `git ls-files --others --exclude-standard`

Do not run checks for files that do not yet exist unless the task is creating those files.
Do not use a restricting pathspec while discovering changed paths; validate scope only after collecting the complete tracked and untracked path set.

## Coverage requirements
- No numeric code-coverage threshold exists because the repository currently defines no application test suite.
- Cover every changed governance or packaging contract with a direct structural or behavioral check appropriate to that change.
- Do not substitute file existence for workflow-behavior verification.

## Pre-commit checks
- Run `git diff --check`.
- Validate every changed JSON file with `python -m json.tool <path>`.
- Require a clean worktree before scoped mutation unless the governing task explicitly records an approved pre-existing state.
- Confirm the immutable pre-task `BASE_SHA` was recorded before mutation and was not recomputed afterward.
- Validate the union of `git diff --name-only "$BASE_SHA" --` and `git ls-files --others --exclude-standard` against the authorized task scope.
- Confirm no secret or credential material is present.
- Confirm documentation claims match repository state.

## Verification contract
### plugin-packaging
- PASS only if changed manifests parse, referenced paths exist when required, and the documented approval boundary is preserved.
### skill-bundle-update
- PASS only if provenance is explicit, the pre-task base is immutable, the complete tracked-plus-untracked task path set contains only the authorized bundle, required files remain present, and no root or neighboring-bundle drift occurred.
### governance-change
- PASS only if cross-references resolve, `AGENTS.md` is ≤100 lines, `CLAUDE.md` is ≤30 lines, and rules do not contradict the README workflow boundary.
### documentation
- PASS only if changed claims are supported by current repository state.
### security-review
- PASS only if findings are evidence-grounded and the review itself remains read-only.

## Regression policy
- Do not break existing valid repository contracts to satisfy a new check.
- Fix implementation defects before weakening verification.
- Change a test or verification rule only when evidence shows the rule is incorrect or the governing contract intentionally changed.
- Stop and report BLOCKED when required verification cannot be performed.

## Assumptions
- Shell commands use a Git-capable command environment.
- Python 3 is available for portable path and JSON validation.
- No CI workflow or automated application test suite is currently defined.
