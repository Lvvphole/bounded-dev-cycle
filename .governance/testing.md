# Testing and Verification Policy

## Test commands
Run from the repository root as applicable:
- `git diff --check`
- `python -c "from pathlib import Path; assert Path('README.md').is_file()"`
- `python -m json.tool .codex-plugin/plugin.json`
- `python -m json.tool .agents/plugins/marketplace.json`
- `python -c "from pathlib import Path; assert all(Path(p).is_file() for p in ['skills/scout-agent/SKILL.md','skills/plan/SKILL.md','skills/build-agent/SKILL.md'])"`
- Full-Chain Acceptance Process: the sole `bug-fix` chain-continuity acceptance authority. Materialize `.governance/tests/test-bug-fix-contract.py` from immutable `57c0108ebb13e5adf7f0ead676a3818e4a0e341e` to a path outside the repository; verify its raw-file SHA-256 equals `97c32e8016ab24b4d3bc845edaaa6ea1248b43eb642409bc042ca6fd886afc73`; make that file read-only. Materialize the frozen behavioral oracle from immutable `09aeae77ec63cb9562080bcf4aa8df3635d87f49`; verify its raw-file SHA-256 equals `1980420dc5a0648cb1a7fc7ef65ab9ddacd062656b8abc34dc12fbac76b356ea`; make that file read-only. Run `python <full-chain-acceptance-process> --repo . --pre-ref <faulty-baseline-ref> --frozen-oracle-sha256 <sha256> --frozen-oracle-process <frozen-behavioral-oracle> --attempt <n>`. Attempt 2 or later must repeat `--previous-evidence-record <path>` once for every prior canonical v4 evidence record in attempt order. The worktree verifier is not acceptance authority unless its bytes are independently proven identical to the pinned Full-Chain Acceptance Process.

For scoped mutation tasks, capture the immutable pre-task commit as `BASE_SHA` before the first mutation, then run:
- `git diff --check "$BASE_SHA" --`.
- `git diff --name-only "$BASE_SHA" --`.
- `git ls-files --others --exclude-standard`.

Do not run checks for files that do not yet exist unless the task is creating those files.
Do not use a restricting pathspec while discovering changed paths; validate scope only after collecting the complete tracked and untracked path set.

## Coverage requirements
- No numeric code-coverage threshold exists because the repository currently defines no application test suite.
- The absence of a repository-wide application suite does not waive the targeted oracle or affected regression set required for a `bug-fix` task.
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
### bug-fix
- Before the first repair mutation, freeze the targeted failing oracle and the complete authorized repair path set.
- The frozen targeted behavioral oracle is `.governance/tests/test-bug-fix-contract.py` at immutable `09aeae77ec63cb9562080bcf4aa8df3635d87f49`, raw-file SHA-256 `1980420dc5a0648cb1a7fc7ef65ab9ddacd062656b8abc34dc12fbac76b356ea`, schema `bounded-dev-cycle/bug-fix-governance-regression/v4`. Preserve those bytes and semantics unchanged.
- The Full-Chain Acceptance Process is `.governance/tests/test-bug-fix-contract.py` at immutable `57c0108ebb13e5adf7f0ead676a3818e4a0e341e`, raw-file SHA-256 `97c32e8016ab24b4d3bc845edaaa6ea1248b43eb642409bc042ca6fd886afc73`. It is authoritative only for complete predecessor-chain continuity and delegates the behavioral verdict to the frozen targeted oracle.
- Materialize both processes outside the repository, independently SHA-verify each against its pinned identity, and make both read-only before execution. Do not execute historical verifier content in-process.
- Every attempt must bind the same frozen targeted-oracle SHA-256 derived from the immutable faulty baseline verifier bytes.
- `BUGFIX-REGRESSION-SET`: Freeze the regression set before the first repair mutation as the union of the targeted failing oracle, every existing verifier named by repository governance, the task, or the approved plan for each changed path or contract, and every existing test that directly imports, calls, or exercises the changed public interface. Do not substitute unrelated repository-wide checks for this set or broaden it without new evidence.
- Reuse an existing test when it directly expresses the defect. If no existing test can express the targeted failure, a new regression test file is permitted only when the task or approved plan explicitly authorizes that exact path and purpose; otherwise report `BLOCKED`.
- Compute `PRE_REPAIR_SHA256` before the first repair mutation and `POST_REPAIR_SHA256` on the final candidate from the same frozen path set. For each path, hash raw file bytes; represent a missing path as `null`; sort repository-relative paths bytewise; SHA-256 the canonical JSON object of `path -> content_sha256_or_null` using sorted keys and separators `(',', ':')`.
- `BUGFIX-EVIDENCE-CHAIN`: Emit canonical v4 JSON evidence containing `schema`, `status`, `attempt`, `pre_repair_sha256`, `post_repair_sha256`, `previous_evidence_sha256`, targeted-oracle identity and baseline/candidate results, the frozen regression-set results, repository-required checks, complete scope-validation result, and `evidence_sha256`. Compute `evidence_sha256` as SHA-256 of that record with `evidence_sha256` omitted, sorted keys, and separators `(',', ':')`.
- Attempt 1 must set `previous_evidence_sha256` to `null`.
- Attempt 2 or later must supply the immediately preceding canonical evidence record as part of the complete ordered predecessor set. Repeat `--previous-evidence-record <path>` for every prior attempt exactly once, in attempt order. The Full-Chain Acceptance Process must require exactly `n-1` records for attempt `n`, rehash every record, require canonical v4 schema and fields, require attempts `1..n-1` in order, require the same frozen `pre_repair_sha256`, require the same frozen targeted-oracle SHA-256, recompute each predecessor status as `FAIL`, and require every `previous_evidence_sha256` to equal the digest of the independently validated prior record. Only after the complete chain validates may it delegate to the frozen behavioral oracle with attempt `n-1` as that oracle's immediate predecessor.
- Never accept a caller-supplied hash alone as chain evidence.
- The final record emitted by the frozen behavioral oracle must extend the validated complete chain: attempt, pre-repair state, targeted-oracle identity, and `previous_evidence_sha256` must match the successor's validated inputs. Final PASS still requires the frozen behavioral oracle itself to return PASS/exit 0.
- A changed SHA-256 is identity evidence only; it is not repair evidence unless the same targeted oracle changes from FAIL on the bound faulty state to PASS on the bound candidate and the frozen regression set passes.
- `BUGFIX-PASS`: PASS only if the targeted oracle fails on `PRE_REPAIR_SHA256`, the same oracle passes on `POST_REPAIR_SHA256`, `PRE_REPAIR_SHA256 != POST_REPAIR_SHA256`, every member of the frozen regression set passes on the final candidate, all repository-required checks pass, complete tracked-plus-untracked scope validation passes, no valid verifier was weakened or skipped, and the SHA-256 evidence chain validates.
- `BUGFIX-FULL-CHAIN-REGRESSION`: Before declaring the successor authority valid, prove externally that attempt 3 rejects a canonical FAIL attempt-2 record whose `previous_evidence_sha256` is arbitrary/nonexistent even when that attempt-2 record is correctly re-signed; also prove that a valid canonical `1 -> 2 -> 3` chain passes chain continuity and reaches the frozen behavioral oracle.
- Report `BLOCKED` when a meaningful targeted oracle, required regression member, required hash, or required verification cannot be established without exceeding authority or weakening a valid contract.
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
- No repository-wide application test suite is currently defined; `bug-fix` verification is selected per the contract above.
