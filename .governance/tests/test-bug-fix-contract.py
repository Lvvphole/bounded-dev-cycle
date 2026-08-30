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

SCHEMA = "bounded-dev-cycle/bug-fix-governance-regression/v2"
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


def evaluate_state(raw: dict[str, bytes | None]) -> list[dict[str, object]]:
    context_bytes = raw["CONTEXT.md"]
    testing_bytes = raw[".governance/testing.md"]
    script_bytes = raw[".governance/tests/test-bug-fix-contract.py"]
    context = "" if context_bytes is None else context_bytes.decode("utf-8")
    testing = "" if testing_bytes is None else testing_bytes.decode("utf-8")
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
        {"id": "regression-set-defined", "pass": "BUGFIX-REGRESSION-SET" in contract},
        {"id": "complete-pass-criterion", "pass": "BUGFIX-PASS" in contract},
        {"id": "sha256-evidence-chain", "pass": "BUGFIX-EVIDENCE-CHAIN" in contract},
        {
            "id": "structured-evidence-output",
            "pass": REQUIRED_OUTPUT_FIELDS.issubset(schema_fields),
        },
    ]


def status_for(checks: list[dict[str, object]]) -> str:
    return "PASS" if all(item["pass"] is True for item in checks) else "FAIL"


def repository_checks(root: Path, pre_ref: str) -> list[dict[str, object]]:
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
    parser.add_argument("--previous-evidence-sha256")
    args = parser.parse_args()

    previous = args.previous_evidence_sha256
    if previous is not None and not HEX64.fullmatch(previous):
        raise SystemExit("previous evidence SHA-256 must be 64 lowercase hex characters")

    root = Path(args.repo).resolve()
    git(root, "rev-parse", "--verify", f"{args.pre_ref}^{{commit}}")

    pre = state_files(root, args.pre_ref)
    post = state_files(root, None)
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
    required_checks = repository_checks(root, args.pre_ref)
    scope_validation = scope_result(root, args.pre_ref)
    pre_hash = state_sha256(pre)
    post_hash = state_sha256(post)
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
