#!/usr/bin/env python3
"""Validate the deterministic structure of a Build Agent PLAN_READY handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

SCHEMA = "build-agent/v2"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_STATES = {"AUTHORIZED", "APPROVAL_GATED", "UNAUTHORIZED"}
VERIFIER_CLASSES = {"DETERMINISTIC", "DECLARED_NONDETERMINISTIC"}


def require(obj: dict, fields: tuple[str, ...], prefix: str, errors: list[str]) -> None:
    errors.extend(f"{prefix} missing field: {field}" for field in fields if field not in obj)


def extract_manifest(text: str) -> dict:
    headings = list(re.finditer(r"^## Build manifest\s*$", text, re.MULTILINE))
    if len(headings) != 1:
        raise ValueError("expected exactly one exact '## Build manifest' section")
    start = headings[0].end()
    next_heading = re.search(r"^## (?!Build manifest\s*$).+$", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    section = text[start:end]
    match = re.search(r"```json\s*(\{.*?\})\s*```", section, re.DOTALL)
    if not match:
        raise ValueError("missing fenced JSON Build manifest")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("Build manifest must be a JSON object")
    return value



def validate_repo_path(value: object, prefix: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{prefix} must be a non-empty repository-relative path")
        return None
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    canonical = path.as_posix()
    if (
        path.is_absolute()
        or ".." in path.parts
        or path == PurePosixPath(".")
        or re.match(r"^[A-Za-z]:/", canonical)
        or normalized != canonical
    ):
        errors.append(f"{prefix} must be a canonical repository-relative path without ..")
        return None
    return canonical

def validate_actions(value: object, prefix: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, list):
        errors.append(f"{prefix} must be an array")
        return {}
    states: dict[str, str] = {}
    for index, item in enumerate(value):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object")
            continue
        require(item, ("action", "state", "owner", "evidence_ref"), item_prefix, errors)
        if item.get("state") not in AUTHORITY_STATES:
            errors.append(f"{item_prefix}.state is invalid")
        if isinstance(item.get("action"), str):
            action = item["action"]
            if action in states:
                errors.append(f"{item_prefix}.action duplicates protected action: {action}")
            states[action] = item.get("state", "")
    return states


def validate_binding(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("source_binding must be an object")
        return
    require(value, ("commit", "staged_diff_sha256", "unstaged_diff_sha256", "untracked_manifest_sha256", "dirty_submodule_manifest_sha256", "excluded_plan_path"), "source_binding", errors)
    if not value.get("commit"):
        errors.append("source_binding.commit must be non-empty")
    validate_repo_path(value.get("excluded_plan_path"), "source_binding.excluded_plan_path", errors)
    for field in ("staged_diff_sha256", "unstaged_diff_sha256", "untracked_manifest_sha256", "dirty_submodule_manifest_sha256"):
        if field in value and not SHA256_RE.fullmatch(str(value[field])):
            errors.append(f"source_binding.{field} must be a lowercase SHA-256")


def validate_increment(value: object, index: int, errors: list[str]) -> str | None:
    prefix = f"increments[{index}]"
    if not isinstance(value, dict):
        errors.append(f"{prefix} must be an object")
        return None
    require(value, ("id", "objective", "obligations", "dependencies", "files", "actions", "acceptance_criteria", "verifier", "budgets", "checkpoint", "stateful", "protected_actions", "recovery"), prefix, errors)
    inc_id = value.get("id")
    if not isinstance(inc_id, str) or not inc_id:
        errors.append(f"{prefix}.id must be non-empty")
        inc_id = None
    for field in ("objective", "checkpoint"):
        if not value.get(field):
            errors.append(f"{prefix}.{field} must be non-empty")
    for field in ("obligations", "dependencies", "actions", "acceptance_criteria"):
        items = value.get(field)
        if not isinstance(items, list) or (field != "dependencies" and not items):
            errors.append(f"{prefix}.{field} must be {'an array' if field == 'dependencies' else 'a non-empty array'}")
    files = value.get("files")
    if not isinstance(files, list) or not files or len(files) > 5:
        errors.append(f"{prefix}.files must contain 1 to 5 paths")
    else:
        for file_index, file_path in enumerate(files):
            validate_repo_path(file_path, f"{prefix}.files[{file_index}]", errors)
    for action_index, action in enumerate(value.get("actions", [])):
        if not isinstance(action, dict) or not action.get("instruction") or not action.get("postcondition"):
            errors.append(f"{prefix}.actions[{action_index}] needs instruction and postcondition")

    verifier = value.get("verifier")
    if not isinstance(verifier, dict):
        errors.append(f"{prefix}.verifier must be an object")
    else:
        require(verifier, ("reference", "oracle", "class"), f"{prefix}.verifier", errors)
        verifier_class = verifier.get("class")
        if verifier_class not in VERIFIER_CLASSES:
            errors.append(f"{prefix}.verifier.class is invalid")
        if not verifier.get("reference") or not verifier.get("oracle"):
            errors.append(f"{prefix}.verifier reference and oracle must be non-empty")
        if verifier_class == "DECLARED_NONDETERMINISTIC":
            protocol = verifier.get("protocol")
            required = {"trials", "accept_if", "candidate_state", "stopping_rule"}
            if not isinstance(protocol, dict) or not required.issubset(protocol):
                errors.append(f"{prefix}.verifier.protocol is incomplete")
            else:
                trials = protocol["trials"]
                if isinstance(trials, bool) or not isinstance(trials, int) or trials <= 0:
                    errors.append(f"{prefix}.verifier.protocol.trials must be a positive integer")
                for field in ("accept_if", "candidate_state", "stopping_rule"):
                    item = protocol[field]
                    if not isinstance(item, str) or not item.strip():
                        errors.append(f"{prefix}.verifier.protocol.{field} must be a non-empty string")

    budgets = value.get("budgets")
    budget_fields = ("repair_attempts", "command_timeout_seconds", "increment_timeout_seconds")
    if not isinstance(budgets, dict):
        errors.append(f"{prefix}.budgets must be an object")
    else:
        require(budgets, budget_fields, f"{prefix}.budgets", errors)
        for field in budget_fields:
            amount = budgets.get(field)
            if not isinstance(amount, int) or amount <= 0:
                errors.append(f"{prefix}.budgets.{field} must be a positive integer")

    validate_actions(value.get("protected_actions"), f"{prefix}.protected_actions", errors)
    stateful, recovery = value.get("stateful"), value.get("recovery")
    if not isinstance(stateful, bool):
        errors.append(f"{prefix}.stateful must be a boolean")
    elif stateful:
        if not isinstance(recovery, dict):
            errors.append(f"{prefix}.recovery must be an object for stateful work")
        else:
            require(recovery, ("reference", "oracle"), f"{prefix}.recovery", errors)
    elif recovery is not None:
        errors.append(f"{prefix}.recovery must be null when stateful is false")
    return inc_id


def validate_task_list(value: object, increment_ids: list[str], errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("task_list must be an object")
        return
    require(value, ("target", "preservation_evidence", "entries"), "task_list", errors)
    validate_repo_path(value.get("target"), "task_list.target", errors)
    if not value.get("preservation_evidence"):
        errors.append("task_list.preservation_evidence must be non-empty")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("task_list.entries must be a non-empty array")
        return
    ids = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("increment") or not entry.get("text"):
            errors.append(f"task_list.entries[{index}] needs increment and text")
        elif isinstance(entry["increment"], str):
            ids.append(entry["increment"])
    if sorted(ids) != sorted(increment_ids):
        errors.append("task_list.entries must contain exactly one entry for every increment")


def validate_publication(value: object, allowed_commit_paths: set[str], errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("publication must be an object")
        return
    mode = value.get("mode")
    if mode == "NONE":
        return
    if mode != "OPEN_PR":
        errors.append("publication.mode must be NONE or OPEN_PR")
        return
    fields = ("branch", "base_branch", "commit_message", "commit_paths", "pr_title", "pr_body", "protected_actions")
    require(value, fields, "publication", errors)
    for field in ("branch", "base_branch", "commit_message", "pr_title", "pr_body"):
        if not value.get(field):
            errors.append(f"publication.{field} must be non-empty")
    commit_paths = value.get("commit_paths")
    if not isinstance(commit_paths, list) or not commit_paths:
        errors.append("publication.commit_paths must be a non-empty array")
    else:
        normalized_paths: list[str] = []
        for index, commit_path in enumerate(commit_paths):
            normalized = validate_repo_path(commit_path, f"publication.commit_paths[{index}]", errors)
            if normalized is not None:
                normalized_paths.append(normalized)
        unexpected = sorted(set(normalized_paths) - allowed_commit_paths)
        if unexpected:
            errors.append(f"publication.commit_paths contains paths outside increment files: {unexpected}")
    states = validate_actions(value.get("protected_actions"), "publication.protected_actions", errors)
    for action in ("commit verified candidate", "push task branch", "create pull request", "merge pull request"):
        if action not in states:
            errors.append(f"publication missing protected action: {action}")
    if states.get("merge pull request") != "UNAUTHORIZED":
        errors.append("publication merge pull request must be UNAUTHORIZED")


def validate(manifest: dict) -> list[str]:
    errors: list[str] = []
    require(manifest, ("schema", "completion_authority", "source_binding", "task_list", "increments", "publication"), "manifest", errors)
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must equal {SCHEMA!r}")
    if not manifest.get("completion_authority"):
        errors.append("completion_authority must be non-empty")
    validate_binding(manifest.get("source_binding"), errors)

    increments = manifest.get("increments")
    if not isinstance(increments, list) or not increments:
        errors.append("increments must be a non-empty array")
        return errors
    ids = [validate_increment(item, index, errors) for index, item in enumerate(increments)]
    valid_ids = [item for item in ids if item]
    if len(valid_ids) != len(set(valid_ids)):
        errors.append("increment ids must be unique")
    positions = {inc_id: index for index, inc_id in enumerate(ids) if inc_id}
    for index, increment in enumerate(increments):
        if not isinstance(increment, dict) or not isinstance(increment.get("dependencies"), list):
            continue
        for dependency in increment["dependencies"]:
            if not isinstance(dependency, str):
                errors.append(f"increments[{index}].dependencies must contain only strings")
                continue
            if dependency not in positions:
                errors.append(f"increments[{index}] has unknown dependency: {dependency}")
            elif positions[dependency] >= index:
                errors.append(f"increments[{index}] dependency must appear earlier: {dependency}")
    validate_task_list(manifest.get("task_list"), valid_ids, errors)
    allowed_commit_paths = {
        path.replace("\\", "/")
        for increment in increments
        if isinstance(increment, dict)
        for path in increment.get("files", [])
        if isinstance(path, str)
    }
    validate_publication(manifest.get("publication"), allowed_commit_paths, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", help="PLAN_READY file path, or '-' for stdin")
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read() if args.plan == "-" else Path(args.plan).read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    errors = [] if actual_sha == args.expected_sha256 else ["plan artifact SHA-256 does not match the trusted expected identity"]
    try:
        text = raw.decode("utf-8")
        if next((line.strip() for line in text.splitlines() if line.strip()), "") != "PLAN_READY":
            errors.append("first non-empty line must be exactly PLAN_READY")
        errors.extend(validate(extract_manifest(text)))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    print(json.dumps({"actual_sha256": actual_sha, "errors": errors}, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
