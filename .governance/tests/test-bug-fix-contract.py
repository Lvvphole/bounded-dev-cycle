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

SCHEMA = "bounded-dev-cycle/bug-fix-governance-regression/v3"
STATE_PATHS = (
    "CONTEXT.md",
    ".governance/testing.md",
    ".governance/tests/test-bug-fix-contract.py",
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
REGRESSION_SET_CLAUSES = (
    "Freeze the regression set before the first repair mutation as the union of the targeted failing oracle",
    "Do not substitute unrelated repository-wide checks for this set or broaden it without new evidence.",
)
EVIDENCE_CHAIN_CLAUSES = (
    "Attempt 1 must set `previous_evidence_sha256` to `null`.",
    "Attempt 2 or later must supply the immediately preceding canonical evidence record",
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
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


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


def assignment_dict_keys(script: bytes, variable: str) -> set[str]:
    tree = ast.parse(script.decode("utf-8"))
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


def output_fields(script: bytes) -> set[str]:
    return assignment_dict_keys(script, "evidence") | assignment_dict_keys(script, "output")


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


def validate_canonical_evidence_record(record: dict[str, object]) -> None:
    if set(record) != REQUIRED_OUTPUT_FIELDS:
        raise ValueError("previous evidence record fields do not match the canonical schema")

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

    regression = record["regression_set_results"]
    if not isinstance(regression, list) or not regression or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not item["id"]
        or item.get("baseline") not in {"FAIL", "PASS"}
        or item.get("candidate") not in {"FAIL", "PASS"}
        for item in regression
    ):
        raise ValueError("previous evidence record has invalid regression-set results")

    required_checks = record["repository_required_checks"]
    if not isinstance(required_checks, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not item["id"]
        or item.get("status") not in {"FAIL", "PASS", "NOT_APPLICABLE"}
        for item in required_checks
    ):
        raise ValueError("previous evidence record has invalid repository-required checks")

    scope = record["scope_validation"]
    scope_lists = ("authorized_paths", "changed_paths", "unauthorized_paths")
    if (
        not isinstance(scope, dict)
        or not all(key in scope for key in (*scope_lists, "status"))
        or scope.get("status") not in {"FAIL", "PASS"}
        or any(
            not isinstance(scope[key], list)
            or any(not isinstance(path, str) for path in scope[key])
            for key in scope_lists
        )
    ):
        raise ValueError("previous evidence record has invalid scope validation")


def validate_previous_evidence(
    record: object,
    *,
    current_pre_sha256: str,
    current_attempt: int,
) -> str:
    if not isinstance(record, dict):
        raise ValueError("previous evidence record must be a JSON object")

    validate_canonical_evidence_record(record)
    embedded = record["evidence_sha256"]

    unsigned = dict(record)
    unsigned.pop("evidence_sha256")
    if sha256(canonical_json(unsigned)) != embedded:
        raise ValueError("previous evidence record SHA-256 does not recompute")

    if record["schema"] != SCHEMA:
        raise ValueError("previous evidence record schema does not match")
    if record["status"] != "FAIL":
        raise ValueError("a later repair attempt requires the preceding record to be FAIL")
    if record["attempt"] != current_attempt - 1:
        raise ValueError("previous evidence record is not the immediately preceding attempt")
    if record["pre_repair_sha256"] != current_pre_sha256:
        raise ValueError("previous evidence record does not bind the same pre-repair state")

    return embedded


def load_previous_evidence(
    path: Path | None,
    *,
    current_pre_sha256: str,
    current_attempt: int,
) -> str | None:
    if current_attempt < 1:
        raise SystemExit("--attempt must be at least 1")
    if current_attempt == 1:
        if path is not None:
            raise SystemExit("attempt 1 must not supply --previous-evidence-record")
        return None
    if path is None:
        raise SystemExit("attempt 2 or later requires --previous-evidence-record")

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return validate_previous_evidence(
            record,
            current_pre_sha256=current_pre_sha256,
            current_attempt=current_attempt,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid previous evidence record: {exc}") from exc


def signed_evidence(unsigned: dict[str, object]) -> dict[str, object]:
    return {**unsigned, "evidence_sha256": sha256(canonical_json(unsigned))}


def synthetic_previous_evidence(pre_sha256: str) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": "FAIL",
        "attempt": 1,
        "pre_repair_sha256": pre_sha256,
        "post_repair_sha256": "1" * 64,
        "previous_evidence_sha256": None,
        "targeted_oracle": {
            "sha256": "2" * 64,
            "baseline_result": "FAIL",
            "candidate_result": "FAIL",
        },
        "regression_set_results": [
            {"id": "synthetic", "baseline": "FAIL", "candidate": "FAIL"}
        ],
        "repository_required_checks": [{"id": "synthetic", "status": "PASS"}],
        "scope_validation": {
            "authorized_paths": sorted(AUTHORIZED_PATHS),
            "changed_paths": [],
            "unauthorized_paths": [],
            "status": "PASS",
        },
    }


def negative_previous_evidence_records(
    unsigned: dict[str, object], valid: dict[str, object]
) -> list[dict[str, object]]:
    incomplete = {
        key: unsigned[key]
        for key in ("schema", "status", "attempt", "pre_repair_sha256")
    }
    malformed_target = {**unsigned, "targeted_oracle": {"sha256": "2" * 64}}
    empty_regression = {**unsigned, "regression_set_results": []}
    malformed_regression = {**unsigned, "regression_set_results": [{}]}
    malformed_checks = {**unsigned, "repository_required_checks": [{}]}
    malformed_scope = {**unsigned, "scope_validation": {"status": "PASS"}}
    wrong_attempt = {**unsigned, "attempt": 2}
    wrong_pre = {**unsigned, "pre_repair_sha256": "3" * 64}
    wrong_status = {**unsigned, "status": "PASS"}
    return [
        {**valid, "evidence_sha256": "0" * 64},
        signed_evidence(incomplete),
        signed_evidence(malformed_target),
        signed_evidence(empty_regression),
        signed_evidence(malformed_regression),
        signed_evidence(malformed_checks),
        signed_evidence(malformed_scope),
        signed_evidence(wrong_attempt),
        signed_evidence(wrong_pre),
        signed_evidence(wrong_status),
    ]


def previous_evidence_behavior(script: bytes | None) -> bool:
    if script is None:
        return False
    try:
        tree = ast.parse(script.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False

    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval"}
        for node in ast.walk(tree)
    ):
        return False

    validator = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "validate_canonical_evidence_record"
        ),
        None,
    )
    if validator is None:
        return False

    return any(
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Name)
        and node.operand.id == "regression"
        for node in ast.walk(validator)
    )


def previous_evidence_self_test(pre_sha256: str) -> bool:
    unsigned = synthetic_previous_evidence(pre_sha256)
    valid = signed_evidence(unsigned)
    try:
        accepted = validate_previous_evidence(
            valid,
            current_pre_sha256=pre_sha256,
            current_attempt=2,
        )
    except (TypeError, ValueError):
        return False
    if accepted != valid["evidence_sha256"]:
        return False

    for record in negative_previous_evidence_records(unsigned, valid):
        try:
            validate_previous_evidence(
                record,
                current_pre_sha256=pre_sha256,
                current_attempt=2,
            )
        except (TypeError, ValueError):
            continue
        return False
    return True


def evaluate_state(raw: dict[str, bytes | None]) -> list[dict[str, object]]:
    context_bytes = raw["CONTEXT.md"]
    testing_bytes = raw[".governance/testing.md"]
    script_bytes = raw[".governance/tests/test-bug-fix-contract.py"]
    context = normalized_text(context_bytes)
    testing = normalized_text(testing_bytes)
    route = section(context, "## Task: bug-fix", "## Task:")
    contract = section(testing, "### bug-fix", "### ")
    schema_fields = set() if script_bytes is None else output_fields(script_bytes)

    return [
        {"id": "route-present", "pass": bool(route)},
        {"id": "removal-first", "pass": "BUGFIX-REMOVE-FIRST" in route},
        {"id": "no-invented-files", "pass": "BUGFIX-NO-INVENTED-FILES" in route},
        {"id": "verification-contract-present", "pass": bool(contract)},
        {
            "id": "documented-pre-ref",
            "pass": "--pre-ref <faulty-baseline-ref>" in testing,
        },
        {
            "id": "documented-previous-record",
            "pass": "--previous-evidence-record <path>" in testing,
        },
        {
            "id": "documented-attempt",
            "pass": "--attempt <n>" in testing,
        },
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


def status_for(checks: list[dict[str, object]]) -> str:
    return "PASS" if all(item["pass"] is True for item in checks) else "FAIL"


def repository_checks(
    root: Path,
    pre_ref: str,
    pre_sha256: str,
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
            "status": "PASS" if previous_evidence_self_test(pre_sha256) else "FAIL",
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
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--previous-evidence-record", type=Path)
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    git(root, "rev-parse", "--verify", f"{args.pre_ref}^{{commit}}")

    pre = state_files(root, args.pre_ref)
    post = state_files(root, None)
    pre_hash = state_sha256(pre)
    post_hash = state_sha256(post)
    previous = load_previous_evidence(
        args.previous_evidence_record,
        current_pre_sha256=pre_hash,
        current_attempt=args.attempt,
    )

    baseline_checks = evaluate_state(pre)
    candidate_checks = evaluate_state(post)
    baseline_result = status_for(baseline_checks)
    candidate_result = status_for(candidate_checks)

    regression_set_results = [
        {
            "id": candidate["id"],
            "baseline": "PASS" if baseline["pass"] is True else "FAIL",
            "candidate": "PASS" if candidate["pass"] is True else "FAIL",
        }
        for baseline, candidate in zip(baseline_checks, candidate_checks, strict=True)
    ]
    required_checks = repository_checks(root, args.pre_ref, pre_hash)
    scope_validation = scope_result(root, args.pre_ref)
    oracle_hash = sha256(Path(__file__).read_bytes())

    status = (
        "PASS"
        if baseline_result == "FAIL"
        and candidate_result == "PASS"
        and pre_hash != post_hash
        and all(item["candidate"] == "PASS" for item in regression_set_results)
        and all(item["status"] != "FAIL" for item in required_checks)
        and scope_validation["status"] == "PASS"
        else "FAIL"
    )

    evidence = {
        "schema": SCHEMA,
        "status": status,
        "attempt": args.attempt,
        "pre_repair_sha256": pre_hash,
        "post_repair_sha256": post_hash,
        "previous_evidence_sha256": previous,
        "targeted_oracle": {
            "sha256": oracle_hash,
            "baseline_result": baseline_result,
            "candidate_result": candidate_result,
        },
        "regression_set_results": regression_set_results,
        "repository_required_checks": required_checks,
        "scope_validation": scope_validation,
    }
    evidence_sha256 = sha256(canonical_json(evidence))
    output = {**evidence, "evidence_sha256": evidence_sha256}
    print(canonical_json(output).decode("ascii"))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
