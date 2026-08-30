#!/usr/bin/env python3
"""Verify the bug-fix governance contract with hash-bound repair evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "bounded-dev-cycle/bug-fix-governance-regression/v5"
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
REGRESSION_SET_CLAUSES = (
    "Freeze the regression set before the first repair mutation as the union of the targeted failing oracle",
    "Do not substitute unrelated repository-wide checks for this set or broaden it without new evidence.",
)
EVIDENCE_CHAIN_CLAUSES = (
    "Attempt 1 must set `previous_evidence_sha256` to `null`.",
    "Attempt 2 or later must supply every earlier canonical evidence record in attempt order",
    "Every attempt must bind the same frozen targeted-oracle SHA-256 derived from the immutable faulty baseline verifier bytes.",
    "Never accept a caller-supplied hash alone as chain evidence.",
)
PASS_CLAUSE = (
    "`BUGFIX-PASS`: PASS only if the targeted oracle fails on `PRE_REPAIR_SHA256`, "
    "the same oracle passes on `POST_REPAIR_SHA256`, "
    "`PRE_REPAIR_SHA256 != POST_REPAIR_SHA256`, "
    "every member of the frozen regression set passes on the final candidate, "
    "all repository-required checks pass, "
    "complete tracked-plus-untracked scope validation passes, "
    "no valid verifier was weakened or skipped, "
    "and the SHA-256 evidence chain validates."
)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_text(data: bytes | None) -> str:
    if data is None:
        return ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def section(text: str, start: str, next_prefix: str) -> str:
    marker = f"{start}\n"
    begin = text.find(marker)
    if begin < 0:
        return ""
    begin += len(marker)
    end = text.find(f"\n{next_prefix}", begin)
    return text[begin:] if end < 0 else text[begin:end]


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


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    return next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ),
        None,
    )


def calls_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == name
        for item in ast.walk(node)
    )


def previous_evidence_behavior(script: bytes | None) -> bool:
    tree = parse_python_source(script)
    if tree is None:
        return False
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval"}
        for node in ast.walk(tree)
    ):
        return False

    derive = function_node(tree, "derive_status")
    validate = function_node(tree, "validate_previous_evidence")
    validate_chain = function_node(tree, "validate_evidence_chain")
    frozen_oracle = function_node(tree, "frozen_oracle_sha256")
    output = function_node(tree, "output_fields")
    main = function_node(tree, "main")
    if any(
        node is None
        for node in (derive, validate, validate_chain, frozen_oracle, output, main)
    ):
        return False

    return (
        calls_name(validate, "derive_status")
        and calls_name(validate_chain, "validate_previous_evidence")
        and calls_name(main, "derive_status")
        and calls_name(main, "frozen_oracle_sha256")
        and calls_name(main, "load_previous_evidence")
        and calls_name(output, "parse_python_source")
    )


def read_ref_file(root: Path, ref: str, relative: str) -> bytes | None:
    entry = git(root, "ls-tree", "-z", ref, "--", relative).stdout
    if not entry:
        return None
    return git(root, "show", f"{ref}:{relative}").stdout


def read_worktree_file(root: Path, relative: str) -> bytes | None:
    path = root / relative
    return path.read_bytes() if path.is_file() else None


def state_files(root: Path, ref: str | None) -> dict[str, bytes | None]:
    reader = (
        (lambda relative: read_worktree_file(root, relative))
        if ref is None
        else (lambda relative: read_ref_file(root, ref, relative))
    )
    return {relative: reader(relative) for relative in STATE_PATHS}


def state_sha256(raw: dict[str, bytes | None]) -> str:
    manifest = {
        path: None if content is None else sha256(content)
        for path, content in sorted(raw.items())
    }
    return sha256(canonical_json(manifest))


def frozen_oracle_sha256(pre_state: dict[str, bytes | None]) -> str:
    verifier = pre_state.get(VERIFIER_PATH)
    if verifier is None:
        raise ValueError("faulty baseline does not contain the verifier required to freeze the oracle")
    return sha256(verifier)


def validate_regression_results(regression: object) -> None:
    if not isinstance(regression, list) or not regression:
        raise ValueError("previous evidence record has invalid regression-set results")

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
            raise ValueError("previous evidence record has invalid regression-set results")
        ids.append(item["id"])

    if len(ids) != len(set(ids)) or ids != list(REGRESSION_CHECK_IDS):
        raise ValueError("previous evidence record does not bind the frozen regression set")


def validate_required_checks(required_checks: object) -> None:
    if not isinstance(required_checks, list) or not required_checks:
        raise ValueError("previous evidence record has invalid repository-required checks")

    ids: list[str] = []
    for item in required_checks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("previous evidence record has invalid repository-required checks")
        check_id = item["id"]
        ids.append(check_id)

        allowed_statuses = (
            {"FAIL", "PASS"}
            if check_id in NON_OPTIONAL_CHECK_IDS
            else {"FAIL", "PASS", "NOT_APPLICABLE"}
        )
        if item.get("status") not in allowed_statuses:
            raise ValueError("previous evidence record has invalid repository-required checks")

        if check_id == "git-diff-check":
            if (
                set(item) != {"id", "status", "exit_code"}
                or not isinstance(item.get("exit_code"), int)
                or isinstance(item.get("exit_code"), bool)
            ):
                raise ValueError("previous evidence record has invalid git-diff-check")
            expected = "PASS" if item["exit_code"] == 0 else "FAIL"
            if item["status"] != expected:
                raise ValueError("previous evidence record has inconsistent git-diff-check")
        elif set(item) != {"id", "status"}:
            raise ValueError("previous evidence record has invalid repository-required checks")

    if len(ids) != len(set(ids)) or ids != list(REPOSITORY_CHECK_IDS):
        raise ValueError("previous evidence record does not bind the required check set")


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
        raise ValueError("previous evidence record has invalid scope validation")

    for key in ("authorized_paths", "changed_paths", "unauthorized_paths"):
        value = scope[key]
        if (
            not isinstance(value, list)
            or any(not isinstance(path, str) or not path for path in value)
            or value != sorted(set(value))
        ):
            raise ValueError("previous evidence record has invalid scope validation")

    if scope["authorized_paths"] != sorted(AUTHORIZED_PATHS):
        raise ValueError("previous evidence record does not bind the authorized path set")

    expected_unauthorized = sorted(
        set(scope["changed_paths"]) - set(scope["authorized_paths"])
    )
    if scope["unauthorized_paths"] != expected_unauthorized:
        raise ValueError("previous evidence record has inconsistent scope paths")

    expected_status = derive_scope_status(scope)
    if scope.get("status") != expected_status:
        raise ValueError("previous evidence record has inconsistent scope status")


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
        raise ValueError("previous evidence record fields do not match the canonical schema")
    if record.get("schema") != SCHEMA:
        raise ValueError("previous evidence record schema does not match")
    if record.get("status") not in {"FAIL", "PASS"}:
        raise ValueError("previous evidence record has an invalid status")

    attempt = record["attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError("previous evidence record has an invalid attempt")

    for field in ("pre_repair_sha256", "post_repair_sha256", "evidence_sha256"):
        value = record[field]
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError(f"previous evidence record has an invalid {field}")

    previous = record["previous_evidence_sha256"]
    if attempt == 1:
        if previous is not None:
            raise ValueError("attempt 1 predecessor evidence must not link to an earlier record")
    elif not isinstance(previous, str) or not HEX64.fullmatch(previous):
        raise ValueError("later predecessor evidence must contain a valid previous_evidence_sha256")

    targeted = record["targeted_oracle"]
    if not isinstance(targeted, dict) or set(targeted) != {
        "sha256",
        "baseline_result",
        "candidate_result",
    }:
        raise ValueError("previous evidence record has an invalid targeted_oracle")
    if not isinstance(targeted["sha256"], str) or not HEX64.fullmatch(targeted["sha256"]):
        raise ValueError("previous evidence record has an invalid targeted oracle SHA-256")
    if targeted["baseline_result"] not in {"FAIL", "PASS"} or targeted[
        "candidate_result"
    ] not in {"FAIL", "PASS"}:
        raise ValueError("previous evidence record has invalid targeted oracle results")

    validate_regression_results(record["regression_set_results"])
    validate_required_checks(record["repository_required_checks"])
    validate_scope(record["scope_validation"])


def validate_previous_evidence(
    record: object,
    *,
    expected_attempt: int,
    current_pre_sha256: str,
    frozen_oracle: str,
    expected_previous_sha256: str | None,
) -> str:
    if not isinstance(record, dict):
        raise ValueError("previous evidence record must be a JSON object")

    validate_canonical_evidence_record(record)
    embedded = record["evidence_sha256"]
    unsigned = dict(record)
    unsigned.pop("evidence_sha256")
    if sha256(canonical_json(unsigned)) != embedded:
        raise ValueError("previous evidence record SHA-256 does not recompute")

    if record["attempt"] != expected_attempt:
        raise ValueError("previous evidence records are not the complete ordered attempt chain")
    if record["pre_repair_sha256"] != current_pre_sha256:
        raise ValueError("previous evidence record does not bind the same pre-repair state")
    if record["targeted_oracle"]["sha256"] != frozen_oracle:
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
    frozen_oracle: str,
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
            frozen_oracle=frozen_oracle,
            expected_previous_sha256=previous_sha256,
        )
    return previous_sha256


def load_previous_evidence(
    paths: list[Path],
    *,
    current_pre_sha256: str,
    current_attempt: int,
    frozen_oracle: str,
) -> str | None:
    records: list[object] = []
    try:
        for path in paths:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        return validate_evidence_chain(
            records,
            current_attempt=current_attempt,
            current_pre_sha256=current_pre_sha256,
            frozen_oracle=frozen_oracle,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid previous evidence chain: {exc}") from exc


def signed_evidence(unsigned: dict[str, object]) -> dict[str, object]:
    return {**unsigned, "evidence_sha256": sha256(canonical_json(unsigned))}


def synthetic_regression_results() -> list[dict[str, object]]:
    return [
        {"id": check_id, "baseline": "FAIL", "candidate": "PASS"}
        for check_id in REGRESSION_CHECK_IDS
    ]


def synthetic_required_checks() -> list[dict[str, object]]:
    return [
        {"id": "git-diff-check", "status": "PASS", "exit_code": 0},
        {"id": "readme-present", "status": "PASS"},
        {"id": "previous-evidence-validation", "status": "PASS"},
        {"id": "malformed-baseline-self-test", "status": "PASS"},
        {"id": "json:.codex-plugin/plugin.json", "status": "NOT_APPLICABLE"},
        {"id": "json:.agents/plugins/marketplace.json", "status": "NOT_APPLICABLE"},
        {"id": "skill-tree", "status": "NOT_APPLICABLE"},
    ]


def synthetic_scope() -> dict[str, object]:
    return {
        "authorized_paths": sorted(AUTHORIZED_PATHS),
        "changed_paths": [VERIFIER_PATH],
        "unauthorized_paths": [],
        "status": "PASS",
    }


def synthetic_fail_evidence(
    pre_sha256: str,
    frozen_oracle: str,
    *,
    attempt: int = 1,
    previous_evidence_sha256: str | None = None,
) -> dict[str, object]:
    post_digit = "1" if attempt % 2 else "2"
    return {
        "schema": SCHEMA,
        "status": "FAIL",
        "attempt": attempt,
        "pre_repair_sha256": pre_sha256,
        "post_repair_sha256": post_digit * 64,
        "previous_evidence_sha256": previous_evidence_sha256,
        "targeted_oracle": {
            "sha256": frozen_oracle,
            "baseline_result": "FAIL",
            "candidate_result": "FAIL",
        },
        "regression_set_results": synthetic_regression_results(),
        "repository_required_checks": synthetic_required_checks(),
        "scope_validation": synthetic_scope(),
    }


def synthetic_pass_evidence(pre_sha256: str, frozen_oracle: str) -> dict[str, object]:
    return {
        **synthetic_fail_evidence(pre_sha256, frozen_oracle),
        "status": "PASS",
        "targeted_oracle": {
            "sha256": frozen_oracle,
            "baseline_result": "FAIL",
            "candidate_result": "PASS",
        },
    }


def negative_previous_evidence_records(
    fail_unsigned: dict[str, object],
    valid_fail: dict[str, object],
    pass_unsigned: dict[str, object],
    frozen_oracle: str,
) -> list[dict[str, object]]:
    incomplete = dict(fail_unsigned)
    incomplete.pop("targeted_oracle")
    extra = {**fail_unsigned, "unexpected": True}
    wrong_type = {**fail_unsigned, "attempt": "1"}
    malformed_target = {**fail_unsigned, "targeted_oracle": {"sha256": frozen_oracle}}
    wrong_oracle = {
        **fail_unsigned,
        "targeted_oracle": {**fail_unsigned["targeted_oracle"], "sha256": "f" * 64},
    }
    empty_regression = {**fail_unsigned, "regression_set_results": []}
    malformed_regression = {**fail_unsigned, "regression_set_results": [{}]}
    duplicate_regression = {
        **fail_unsigned,
        "regression_set_results": [
            *synthetic_regression_results()[:-1],
            {**synthetic_regression_results()[-1], "id": REGRESSION_CHECK_IDS[-2]},
        ],
    }
    malformed_checks = {**fail_unsigned, "repository_required_checks": [{}]}
    malformed_scope = {**fail_unsigned, "scope_validation": {"status": "PASS"}}
    wrong_attempt = {**fail_unsigned, "attempt": 2, "previous_evidence_sha256": "4" * 64}
    wrong_pre = {**fail_unsigned, "pre_repair_sha256": "3" * 64}
    fail_claims_pass = {**fail_unsigned, "status": "PASS"}
    pass_claims_fail = {**pass_unsigned, "status": "FAIL"}
    equal_hash_claims_pass = {
        **pass_unsigned,
        "post_repair_sha256": pass_unsigned["pre_repair_sha256"],
    }

    failing_regression = synthetic_regression_results()
    failing_regression[0] = {**failing_regression[0], "candidate": "FAIL"}
    failing_regression_claims_pass = {
        **pass_unsigned,
        "regression_set_results": failing_regression,
    }
    failing_checks = synthetic_required_checks()
    failing_checks[1] = {"id": "readme-present", "status": "FAIL"}
    failing_check_claims_pass = {
        **pass_unsigned,
        "repository_required_checks": failing_checks,
    }
    unauthorized_scope = {
        "authorized_paths": sorted(AUTHORIZED_PATHS),
        "changed_paths": [VERIFIER_PATH, "outside.txt"],
        "unauthorized_paths": ["outside.txt"],
        "status": "PASS",
    }
    unauthorized_scope_claims_pass = {
        **pass_unsigned,
        "scope_validation": unauthorized_scope,
    }

    return [
        {**valid_fail, "evidence_sha256": "0" * 64},
        signed_evidence(incomplete),
        signed_evidence(extra),
        signed_evidence(wrong_type),
        signed_evidence(malformed_target),
        signed_evidence(wrong_oracle),
        signed_evidence(empty_regression),
        signed_evidence(malformed_regression),
        signed_evidence(duplicate_regression),
        signed_evidence(malformed_checks),
        signed_evidence(malformed_scope),
        signed_evidence(wrong_attempt),
        signed_evidence(wrong_pre),
        signed_evidence(fail_claims_pass),
        signed_evidence(pass_claims_fail),
        signed_evidence(pass_unsigned),
        signed_evidence(equal_hash_claims_pass),
        signed_evidence(failing_regression_claims_pass),
        signed_evidence(failing_check_claims_pass),
        signed_evidence(unauthorized_scope_claims_pass),
    ]


def evidence_validation_self_test(pre_sha256: str, frozen_oracle: str) -> bool:
    fail_unsigned = synthetic_fail_evidence(pre_sha256, frozen_oracle)
    valid_fail = signed_evidence(fail_unsigned)
    pass_unsigned = synthetic_pass_evidence(pre_sha256, frozen_oracle)

    try:
        if validate_evidence_chain(
            [valid_fail],
            current_attempt=2,
            current_pre_sha256=pre_sha256,
            frozen_oracle=frozen_oracle,
        ) != valid_fail["evidence_sha256"]:
            return False
    except (TypeError, ValueError):
        return False

    for record in negative_previous_evidence_records(
        fail_unsigned,
        valid_fail,
        pass_unsigned,
        frozen_oracle,
    ):
        try:
            validate_previous_evidence(
                record,
                expected_attempt=1,
                current_pre_sha256=pre_sha256,
                frozen_oracle=frozen_oracle,
                expected_previous_sha256=None,
            )
        except (TypeError, ValueError):
            continue
        return False

    attempt_two_unsigned = synthetic_fail_evidence(
        pre_sha256,
        frozen_oracle,
        attempt=2,
        previous_evidence_sha256=valid_fail["evidence_sha256"],
    )
    attempt_two = signed_evidence(attempt_two_unsigned)
    try:
        if validate_evidence_chain(
            [valid_fail, attempt_two],
            current_attempt=3,
            current_pre_sha256=pre_sha256,
            frozen_oracle=frozen_oracle,
        ) != attempt_two["evidence_sha256"]:
            return False
    except (TypeError, ValueError):
        return False

    broken_link = signed_evidence(
        {**attempt_two_unsigned, "previous_evidence_sha256": "4" * 64}
    )
    for broken_chain in (
        [valid_fail, broken_link],
        [attempt_two],
        [attempt_two, valid_fail],
    ):
        try:
            validate_evidence_chain(
                broken_chain,
                current_attempt=3,
                current_pre_sha256=pre_sha256,
                frozen_oracle=frozen_oracle,
            )
        except (TypeError, ValueError):
            continue
        return False
    return True


def evaluate_state(raw: dict[str, bytes | None]) -> list[dict[str, object]]:
    context_bytes = raw["CONTEXT.md"]
    testing_bytes = raw[".governance/testing.md"]
    script_bytes = raw[VERIFIER_PATH]

    context = normalized_text(context_bytes)
    testing = normalized_text(testing_bytes)
    route = section(context, "## Task: bug-fix", "## Task:")
    contract = section(testing, "### bug-fix", "### ")
    schema_fields = output_fields(script_bytes)

    return [
        {"id": "route-present", "pass": bool(route)},
        {"id": "removal-first", "pass": "BUGFIX-REMOVE-FIRST" in route},
        {"id": "no-invented-files", "pass": "BUGFIX-NO-INVENTED-FILES" in route},
        {"id": "verification-contract-present", "pass": bool(contract)},
        {
            "id": "documented-pre-ref",
            "pass": "--pre-ref <faulty-baseline-ref>" in testing
            and "--frozen-oracle-sha256 <sha256>" in testing,
        },
        {
            "id": "documented-previous-record",
            "pass": "repeat `--previous-evidence-record <path>`" in testing,
        },
        {"id": "documented-attempt", "pass": "--attempt <n>" in testing},
        {
            "id": "regression-set-defined",
            "pass": all(clause in contract for clause in REGRESSION_SET_CLAUSES),
        },
        {"id": "complete-pass-criterion", "pass": PASS_CLAUSE in contract},
        {
            "id": "sha256-evidence-chain",
            "pass": all(clause in contract for clause in EVIDENCE_CHAIN_CLAUSES),
        },
        {
            "id": "structured-evidence-output",
            "pass": REQUIRED_OUTPUT_FIELDS.issubset(schema_fields),
        },
        {
            "id": "previous-evidence-behavior",
            "pass": previous_evidence_behavior(script_bytes),
        },
    ]


def malformed_baseline_self_test() -> bool:
    for malformed in (b"\xff", b"def :"):
        raw = {
            "CONTEXT.md": b"",
            ".governance/testing.md": b"",
            VERIFIER_PATH: malformed,
        }
        try:
            checks = evaluate_state(raw)
        except Exception:
            return False
        by_id = {item["id"]: item["pass"] for item in checks}
        if by_id.get("structured-evidence-output") is not False:
            return False
        if by_id.get("previous-evidence-behavior") is not False:
            return False
    return True


def status_for(checks: list[dict[str, object]]) -> str:
    return "PASS" if all(item["pass"] is True for item in checks) else "FAIL"


def repository_checks(
    root: Path,
    pre_ref: str,
    pre_sha256: str,
    frozen_oracle: str,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    diff_check = git(root, "diff", "--check", pre_ref, "--", check=False)
    checks.append(
        {
            "id": "git-diff-check",
            "status": "PASS" if diff_check.returncode == 0 else "FAIL",
            "exit_code": diff_check.returncode,
        }
    )
    checks.append(
        {
            "id": "readme-present",
            "status": "PASS" if (root / "README.md").is_file() else "FAIL",
        }
    )
    checks.append(
        {
            "id": "previous-evidence-validation",
            "status": "PASS"
            if evidence_validation_self_test(pre_sha256, frozen_oracle)
            else "FAIL",
        }
    )
    checks.append(
        {
            "id": "malformed-baseline-self-test",
            "status": "PASS" if malformed_baseline_self_test() else "FAIL",
        }
    )

    for relative in (".codex-plugin/plugin.json", ".agents/plugins/marketplace.json"):
        path = root / relative
        if not path.is_file():
            checks.append({"id": f"json:{relative}", "status": "NOT_APPLICABLE"})
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            checks.append({"id": f"json:{relative}", "status": "FAIL"})
        else:
            checks.append({"id": f"json:{relative}", "status": "PASS"})

    required_skills = (
        "skills/scout-agent/SKILL.md",
        "skills/plan/SKILL.md",
        "skills/build-agent/SKILL.md",
    )
    if not (root / "skills").exists():
        checks.append({"id": "skill-tree", "status": "NOT_APPLICABLE"})
    else:
        checks.append(
            {
                "id": "skill-tree",
                "status": "PASS"
                if all((root / relative).is_file() for relative in required_skills)
                else "FAIL",
            }
        )
    return checks


def scope_result(root: Path, pre_ref: str) -> dict[str, object]:
    tracked = [
        item.decode("utf-8", "surrogateescape")
        for item in git(root, "diff", "--name-only", "-z", pre_ref, "--").stdout.split(b"\0")
        if item
    ]
    untracked = [
        item.decode("utf-8", "surrogateescape")
        for item in git(
            root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ).stdout.split(b"\0")
        if item
    ]
    changed = sorted(set(tracked) | set(untracked))
    unauthorized = sorted(set(changed) - AUTHORIZED_PATHS)
    return {
        "authorized_paths": sorted(AUTHORIZED_PATHS),
        "changed_paths": changed,
        "unauthorized_paths": unauthorized,
        "status": "PASS" if not unauthorized else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--pre-ref", required=True)
    parser.add_argument("--frozen-oracle-sha256", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument(
        "--previous-evidence-record",
        type=Path,
        action="append",
        default=[],
        help="repeat in attempt order for every prior canonical evidence record",
    )
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    git(root, "rev-parse", "--verify", f"{args.pre_ref}^{{commit}}")

    pre = state_files(root, args.pre_ref)
    post = state_files(root, None)
    pre_hash = state_sha256(pre)
    post_hash = state_sha256(post)

    if not HEX64.fullmatch(args.frozen_oracle_sha256):
        raise SystemExit("--frozen-oracle-sha256 must be a lowercase SHA-256")
    try:
        computed_frozen_oracle = frozen_oracle_sha256(pre)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if computed_frozen_oracle != args.frozen_oracle_sha256:
        raise SystemExit(
            "--frozen-oracle-sha256 does not match the immutable faulty baseline verifier"
        )
    frozen_oracle = args.frozen_oracle_sha256

    previous = load_previous_evidence(
        args.previous_evidence_record,
        current_pre_sha256=pre_hash,
        current_attempt=args.attempt,
        frozen_oracle=frozen_oracle,
    )

    baseline_checks = evaluate_state(pre)
    candidate_checks = evaluate_state(post)
    baseline_result = status_for(baseline_checks)
    candidate_result = status_for(candidate_checks)

    regression_set_results = [
        {
            "id": candidate_check["id"],
            "baseline": "PASS" if baseline_check["pass"] is True else "FAIL",
            "candidate": "PASS" if candidate_check["pass"] is True else "FAIL",
        }
        for baseline_check, candidate_check in zip(
            baseline_checks,
            candidate_checks,
            strict=True,
        )
    ]
    required_checks = repository_checks(root, args.pre_ref, pre_hash, frozen_oracle)
    scope_validation = scope_result(root, args.pre_ref)
    targeted_oracle = {
        "sha256": frozen_oracle,
        "baseline_result": baseline_result,
        "candidate_result": candidate_result,
    }

    status = derive_status(
        pre_repair_sha256=pre_hash,
        post_repair_sha256=post_hash,
        targeted_oracle=targeted_oracle,
        regression_set_results=regression_set_results,
        repository_required_checks=required_checks,
        scope_validation=scope_validation,
    )

    evidence = {
        "schema": SCHEMA,
        "status": status,
        "attempt": args.attempt,
        "pre_repair_sha256": pre_hash,
        "post_repair_sha256": post_hash,
        "previous_evidence_sha256": previous,
        "targeted_oracle": targeted_oracle,
        "regression_set_results": regression_set_results,
        "repository_required_checks": required_checks,
        "scope_validation": scope_validation,
    }
    evidence_sha256 = sha256(canonical_json(evidence))
    output = {**evidence, "evidence_sha256": evidence_sha256}
    validate_canonical_evidence_record(output)
    if derive_status(
        pre_repair_sha256=output["pre_repair_sha256"],
        post_repair_sha256=output["post_repair_sha256"],
        targeted_oracle=output["targeted_oracle"],
        regression_set_results=output["regression_set_results"],
        repository_required_checks=output["repository_required_checks"],
        scope_validation=output["scope_validation"],
    ) != output["status"]:
        raise SystemExit("internal evidence status derivation mismatch")
    print(canonical_json(output).decode("ascii"))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
