# Testing and Verification Policy

## Test commands
Run from the repository root as applicable:
- `git diff --check`
- `python -c "from pathlib import Path; assert Path('README.md').is_file()"`
- `python -m json.tool .codex-plugin/plugin.json`
- `python -m json.tool .agents/plugins/marketplace.json`
- `python -c "from pathlib import Path; assert all(Path(p).is_file() for p in ['skills/scout-agent/SKILL.md','skills/plan/SKILL.md','skills/build-agent/SKILL.md'])"`
- `git diff --name-only -- skills/`

Do not run checks for files that do not yet exist unless the task is creating those files.

## Coverage requirements
- No numeric code-coverage threshold exists because the repository currently defines no application test suite.
- Cover every changed governance or packaging contract with a direct structural or behavioral check appropriate to that change.
- Do not substitute file existence for workflow-behavior verification.

## Pre-commit checks
- Run `git diff --check`.
- Validate every changed JSON file with `python -m json.tool <path>`.
- Confirm changed paths are within authorized scope.
- Confirm no secret or credential material is present.
- Confirm documentation claims match repository state.

## Verification contract
### plugin-packaging
- PASS only if changed manifests parse, referenced paths exist when required, and the documented approval boundary is preserved.
### skill-bundle-update
- PASS only if provenance is explicit, only authorized bundle paths changed, required files remain present, and no neighboring bundle drift occurred.
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
