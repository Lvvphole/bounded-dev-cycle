#!/usr/bin/env python3
"""Validate the complete bug-fix evidence chain, then delegate to the frozen oracle."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "bounded-dev-cycle/bug-fix-governance-regression/v4"
VERIFIER_PATH = ".governance/tests/test-bug-fix-contract.py"
STATE_PATHS = (
    "CONTEXT.md",
    ".governance/testing.md",
    VERIFIER_PATH,
)
AUTHORIZED_PATHS = frozenset(STATE_PATHS)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_OUTPUT_FIELDS = frozenset(
    {
        "schema",
        "status",
        "attempt",
        "pre_repair_sha256",
        "post_repair_sha256",
        "previous_evidence_sha256",
        "targeted_oracle",
        "regression_set_results",
        "repository_required_checks",
        "scope_validation",
        "evidence_sha256",
    }
)
REGRESSION_CHECK_IDS = (
    "route-present",
    "removal-first",
    "no-invented-files",
    "verification-contract-present",
    "documented-pre-ref",
    "documented-previous-record",
    "documented-attempt",
    "regression-set-defined",
    "complete-pass-criterion",
    "sha256-evidence-chain",
    "structured-evidence-output",
    "previous-evidence-behavior",
)
REPOSITORY_CHECK_IDS = (
    "git-diff-check",
    "readme-present",
    "previous-evidence-validation",
    "malformed-baseline-self-test",
    "json:.codex-plugin/plugin.json",
    "json:.agents/plugins/marketplace.json",
    "skill-tree",
)
NON_OPTIONAL_CHECK_IDS = frozenset(
    {
        "git-diff-check",
        "readme-present",
        "previous-evidence-validation",
        "malformed-baseline-self-test",
    }
)
FROZEN_ORACLE_REF = "09aeae77ec63cb9562080bcf4aa8df3635d87f49"
FROZEN_ORACLE_SHA256 = "1980420dc5a0648cb1a7fc7ef65ab9ddacd062656b8abc34dc12fbac76b356ea"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_python_source(script: bytes | None) -> ast.Module | None:
    if script is None:
        return None
    try:
        return ast.parse(script.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def assignment_dict_keys(tree: ast.Module, variable: str) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == variable
            for target in node.targets
        ):
            continue
        return {
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
    return set()


def output_fields(script: bytes | None) -> set[str]:
    tree = parse_python_source(script)
    if tree is None:
        return set()
    return assignment_dict_keys(tree, "evidence") | assignment_dict_keys(tree, "output")


def read_ref_file(root: Path, ref: str, relative: str) -> bytes | None:
    entry = git(root, "ls-tree", "-z", ref, "--", relative).stdout
    if not entry:
        return None
    return git(root, "show", f"{ref}:{relative}").stdout


def state_files(root: Path, ref: str) -> dict[str, bytes | None]:
    return {relative: read_ref_file(root, ref, relative) for relative in STATE_PATHS}


def state_sha256(raw: dict[str, bytes | None]) -> str:
    manifest = {
        path: None if content is None else sha256(content)
        for path, content in sorted(raw.items())
    }
    return sha256(canonical_json(manifest))


def frozen_oracle_sha256(root: Path) -> str:
    verifier = read_ref_file(root, FROZEN_ORACLE_REF, VERIFIER_PATH)
    if verifier is None:
        raise ValueError("frozen oracle ref does not contain the verifier")
    digest = sha256(verifier)
    if digest != FROZEN_ORACLE_SHA256:
        raise ValueError("frozen oracle ref bytes do not match the pinned SHA-256")
    return digest


def assert_frozen_oracle_process(root: Path, process: Path, expected_sha: str) -> Path:
    resolved = process.resolve()
    repo = root.resolve()
    if resolved == repo or repo in resolved.parents:
        raise ValueError("frozen oracle process must be materialized outside the repository")
    try:
        blob = resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f"frozen oracle process is unreadable: {exc}") from exc
    if sha256(blob) != expected_sha:
        raise ValueError("frozen oracle process bytes do not match FROZEN_ORACLE_SHA256")
    return resolved


def run_frozen_oracle_process(
    process: Path,
    *,
    root: Path,
    pre_ref: str,
    attempt: int,
    previous_evidence_record: Path | None,
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "python3",
        str(process),
        "--repo",
        str(root),
        "--pre-ref",
        pre_ref,
        "--attempt",
        str(attempt),
    ]
    if previous_evidence_record is not None:
        command.extend(["--previous-evidence-record", str(previous_evidence_record)])
    return subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def validate_regression_results(regression: object) -> None:
    if not isinstance(regression, list) or not regression:
        raise ValueError("evidence record has invalid regression-set results")
    ids: list[str] = []
    for item in regression:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "baseline", "candidate"}
            or not isinstance(item.get("id"), str)
            or not item["id"]
            or item.get("baseline") not in {"FAIL", "PASS"}
            or item.get("candidate") not in {"FAIL", "PASS"}
        ):
            raise ValueError("evidence record has invalid regression-set results")
        ids.append(item["id"])
    if len(ids) != len(set(ids)) or ids != list(REGRESSION_CHECK_IDS):
        raise ValueError("evidence record does not bind the frozen regression set")


def validate_required_checks(required_checks: object) -> None:
    if not isinstance(required_checks, list) or not required_checks:
        raise ValueError("evidence record has invalid repository-required checks")
    ids: list[str] = []
    for item in required_checks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("evidence record has invalid repository-required checks")
        check_id = item["id"]
        ids.append(check_id)
        allowed_statuses = (
            {"FAIL", "PASS"}
            if check_id in NON_OPTIONAL_CHECK_IDS
            else {"FAIL", "PASS", "NOT_APPLICABLE"}
        )
        if item.get("status") not in allowed_statuses:
            raise ValueError("evidence record has invalid repository-required checks")
        if check_id == "git-diff-check":
            if (
                set(item) != {"id", "status", "exit_code"}
                or not isinstance(item.get("exit_code"), int)
                or isinstance(item.get("exit_code"), bool)
            ):
                raise ValueError("evidence record has invalid git-diff-check")
            expected = "PASS" if item["exit_code"] == 0 else "FAIL"
            if item["status"] != expected:
                raise ValueError("evidence record has inconsistent git-diff-check")
        elif set(item) != {"id", "status"}:
            raise ValueError("evidence record has invalid repository-required checks")
    if len(ids) != len(set(ids)) or ids != list(REPOSITORY_CHECK_IDS):
        raise ValueError("evidence record does not bind the required check set")


def derive_scope_status(scope: dict[str, object]) -> str:
    unauthorized = scope["unauthorized_paths"]
    return "PASS" if isinstance(unauthorized, list) and not unauthorized else "FAIL"


def validate_scope(scope: object) -> None:
    if not isinstance(scope, dict) or set(scope) != {
        "authorized_paths",
        "changed_paths",
        "unauthorized_paths",
        "status",
    }:
        raise ValueError("evidence record has invalid scope validation")
    for key in ("authorized_paths", "changed_paths", "unauthorized_paths"):
        value = scope[key]
        if (
            not isinstance(value, list)
            or any(not isinstance(path, str) or not path for path in value)
            or value != sorted(set(value))
        ):
            raise ValueError("evidence record has invalid scope validation")
    if scope["authorized_paths"] != sorted(AUTHORIZED_PATHS):
        raise ValueError("evidence record does not bind the authorized path set")
    expected_unauthorized = sorted(
        set(scope["changed_paths"]) - set(scope["authorized_paths"])
    )
    if scope["unauthorized_paths"] != expected_unauthorized:
        raise ValueError("evidence record has inconsistent scope paths")
    if scope.get("status") != derive_scope_status(scope):
        raise ValueError("evidence record has inconsistent scope status")


def derive_status(
    *,
    pre_repair_sha256: str,
    post_repair_sha256: str,
    targeted_oracle: dict[str, object],
    regression_set_results: list[dict[str, object]],
    repository_required_checks: list[dict[str, object]],
    scope_validation: dict[str, object],
) -> str:
    return (
        "PASS"
        if targeted_oracle["baseline_result"] == "FAIL"
        and targeted_oracle["candidate_result"] == "PASS"
        and pre_repair_sha256 != post_repair_sha256
        and all(item["candidate"] == "PASS" for item in regression_set_results)
        and all(item["status"] != "FAIL" for item in repository_required_checks)
        and scope_validation["status"] == "PASS"
        else "FAIL"
    )


def validate_canonical_evidence_record(record: dict[str, object]) -> None:
    if set(record) != REQUIRED_OUTPUT_FIELDS:
        raise ValueError("evidence record fields do not match the canonical schema")
    if record.get("schema") != SCHEMA:
        raise ValueError("evidence record schema does not match frozen v4")
    if record.get("status") not in {"FAIL", "PASS"}:
        raise ValueError("evidence record has an invalid status")
    attempt = record["attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("evidence record has an invalid attempt")
    for field in ("pre_repair_sha256", "post_repair_sha256", "evidence_sha256"):
        value = record[field]
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError(f"evidence record has an invalid {field}")
    previous = record["previous_evidence_sha256"]
    if attempt == 1:
        if previous is not None:
            raise ValueError("attempt 1 evidence must not link to an earlier record")
    elif not isinstance(previous, str) or not HEX64.fullmatch(previous):
        raise ValueError("later evidence must contain a valid previous_evidence_sha256")
    targeted = record["targeted_oracle"]
    if not isinstance(targeted, dict) or set(targeted) != {
        "sha256",
        "baseline_result",
        "candidate_result",
    }:
        raise ValueError("evidence record has an invalid targeted_oracle")
    if not isinstance(targeted["sha256"], str) or not HEX64.fullmatch(targeted["sha256"]):
        raise ValueError("evidence record has an invalid targeted oracle SHA-256")
    if targeted["baseline_result"] not in {"FAIL", "PASS"} or targeted[
        "candidate_result"
    ] not in {"FAIL", "PASS"}:
        raise ValueError("evidence record has invalid targeted oracle results")
    validate_regression_results(record["regression_set_results"])
    validate_required_checks(record["repository_required_checks"])
    validate_scope(record["scope_validation"])


def recompute_evidence_sha256(record: dict[str, object]) -> str:
    unsigned = dict(record)
    embedded = unsigned.pop("evidence_sha256")
    computed = sha256(canonical_json(unsigned))
    if computed != embedded:
        raise ValueError("evidence record SHA-256 does not recompute")
    return computed


def validate_previous_evidence(
    record: object,
    *,
    expected_attempt: int,
    current_pre_sha256: str,
    expected_previous_sha256: str | None,
) -> str:
    if not isinstance(record, dict):
        raise ValueError("previous evidence record must be a JSON object")
    validate_canonical_evidence_record(record)
    embedded = recompute_evidence_sha256(record)
    if record["attempt"] != expected_attempt:
        raise ValueError("previous evidence records are not the complete ordered attempt chain")
    if record["pre_repair_sha256"] != current_pre_sha256:
        raise ValueError("previous evidence record does not bind the same pre-repair state")
    if record["targeted_oracle"]["sha256"] != FROZEN_ORACLE_SHA256:
        raise ValueError("previous evidence record does not bind the frozen targeted oracle")
    if record["previous_evidence_sha256"] != expected_previous_sha256:
        raise ValueError("previous evidence record does not link to the validated prior record")
    derived = derive_status(
        pre_repair_sha256=record["pre_repair_sha256"],
        post_repair_sha256=record["post_repair_sha256"],
        targeted_oracle=record["targeted_oracle"],
        regression_set_results=record["regression_set_results"],
        repository_required_checks=record["repository_required_checks"],
        scope_validation=record["scope_validation"],
    )
    if record["status"] != derived:
        raise ValueError("previous evidence record status is inconsistent with its evidence")
    if derived != "FAIL":
        raise ValueError("every preceding repair attempt must derive FAIL")
    return embedded


def validate_evidence_chain(
    records: list[object],
    *,
    current_attempt: int,
    current_pre_sha256: str,
) -> str | None:
    if current_attempt < 1:
        raise ValueError("attempt must be at least 1")
    if len(records) != current_attempt - 1:
        raise ValueError("attempt requires every prior evidence record exactly once")
    previous_sha256: str | None = None
    for expected_attempt, record in enumerate(records, start=1):
        previous_sha256 = validate_previous_evidence(
            record,
            expected_attempt=expected_attempt,
            current_pre_sha256=current_pre_sha256,
            expected_previous_sha256=previous_sha256,
        )
    return previous_sha256


def load_previous_evidence(
    paths: list[Path],
    *,
    current_pre_sha256: str,
    current_attempt: int,
) -> str | None:
    records: list[object] = []
    try:
        for path in paths:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return validate_evidence_chain(
            records,
            current_attempt=current_attempt,
            current_pre_sha256=current_pre_sha256,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid previous evidence chain: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pre-ref", required=True)
    parser.add_argument("--frozen-oracle-sha256", required=True)
    parser.add_argument(
        "--frozen-oracle-process",
        type=Path,
        required=True,
        help="read-only materialized frozen v4 behavioral oracle outside the repository",
    )
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument(
        "--previous-evidence-record",
        type=Path,
        action="append",
        default=[],
        help="repeat in attempt order; every prior canonical v4 evidence record is required",
    )
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    git(root, "rev-parse", "--verify", f"{args.pre_ref}^{{commit}}")
    git(root, "rev-parse", "--verify", f"{FROZEN_ORACLE_REF}^{{commit}}")

    if not HEX64.fullmatch(args.frozen_oracle_sha256):
        raise SystemExit("--frozen-oracle-sha256 must be a lowercase SHA-256")
    try:
        computed_frozen_oracle = frozen_oracle_sha256(root)
        process = assert_frozen_oracle_process(
            root,
            args.frozen_oracle_process,
            computed_frozen_oracle,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if (
        args.frozen_oracle_sha256 != FROZEN_ORACLE_SHA256
        or computed_frozen_oracle != FROZEN_ORACLE_SHA256
    ):
        raise SystemExit("--frozen-oracle-sha256 does not match the frozen behavioral oracle")

    pre_hash = state_sha256(state_files(root, args.pre_ref))
    previous = load_previous_evidence(
        args.previous_evidence_record,
        current_pre_sha256=pre_hash,
        current_attempt=args.attempt,
    )

    predecessor = args.previous_evidence_record[-1] if args.previous_evidence_record else None
    completed = run_frozen_oracle_process(
        process,
        root=root,
        pre_ref=args.pre_ref,
        attempt=args.attempt,
        previous_evidence_record=predecessor,
    )
    if completed.stderr:
        raise SystemExit(completed.stderr.decode("utf-8", "replace"))
    try:
        record = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"frozen oracle process emitted invalid evidence: {exc}") from exc
    if not isinstance(record, dict):
        raise SystemExit("frozen oracle process emitted invalid evidence")

    try:
        validate_canonical_evidence_record(record)
        recompute_evidence_sha256(record)
    except ValueError as exc:
        raise SystemExit(f"frozen oracle process emitted invalid evidence: {exc}") from exc
    if record["attempt"] != args.attempt:
        raise SystemExit("frozen oracle process emitted the wrong attempt")
    if record["pre_repair_sha256"] != pre_hash:
        raise SystemExit("frozen oracle process emitted the wrong pre-repair state")
    if record["previous_evidence_sha256"] != previous:
        raise SystemExit("frozen oracle process did not extend the validated complete chain")
    if record["targeted_oracle"]["sha256"] != FROZEN_ORACLE_SHA256:
        raise SystemExit("frozen oracle process did not bind the frozen targeted oracle")

    derived_status = derive_status(
        pre_repair_sha256=record["pre_repair_sha256"],
        post_repair_sha256=record["post_repair_sha256"],
        targeted_oracle=record["targeted_oracle"],
        regression_set_results=record["regression_set_results"],
        repository_required_checks=record["repository_required_checks"],
        scope_validation=record["scope_validation"],
    )
    if record["status"] != derived_status:
        raise SystemExit("frozen oracle process emitted an inconsistent status")
    expected_returncode = 0 if record["status"] == "PASS" else 1
    if completed.returncode != expected_returncode:
        raise SystemExit("frozen oracle process exit code disagrees with its evidence")

    output = {
        "schema": record["schema"],
        "status": record["status"],
        "attempt": record["attempt"],
        "pre_repair_sha256": record["pre_repair_sha256"],
        "post_repair_sha256": record["post_repair_sha256"],
        "previous_evidence_sha256": record["previous_evidence_sha256"],
        "targeted_oracle": record["targeted_oracle"],
        "regression_set_results": record["regression_set_results"],
        "repository_required_checks": record["repository_required_checks"],
        "scope_validation": record["scope_validation"],
        "evidence_sha256": record["evidence_sha256"],
    }
    print(canonical_json(output).decode("ascii"))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
