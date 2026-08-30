#!/usr/bin/env python3
"""Run deterministic regression tests for the Build Agent handoff contract."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_plan_ready", HERE / "validate-plan-ready.py")
source_binding = load_module("source_binding", HERE / "source-binding.py")


def valid_manifest() -> dict:
    return {
        "schema": "build-agent/v2",
        "completion_authority": "reviewer",
        "source_binding": {
            "commit": "abc",
            "staged_diff_sha256": "0" * 64,
            "unstaged_diff_sha256": "0" * 64,
            "untracked_manifest_sha256": "0" * 64,
            "dirty_submodule_manifest_sha256": "0" * 64,
            "excluded_plan_path": "plans/plan.md",
        },
        "task_list": {
            "target": "tasks/todo.md",
            "preservation_evidence": "preserved",
            "entries": [{"increment": "INC-1", "text": "do work"}],
        },
        "increments": [
            {
                "id": "INC-1",
                "objective": "outcome",
                "obligations": ["OBL-1"],
                "dependencies": [],
                "files": ["src/app.py"],
                "actions": [{"instruction": "change", "postcondition": "works"}],
                "acceptance_criteria": ["works"],
                "verifier": {"reference": "test", "oracle": "fails on defect", "class": "DETERMINISTIC"},
                "budgets": {"repair_attempts": 1, "command_timeout_seconds": 1, "increment_timeout_seconds": 1},
                "checkpoint": "green",
                "stateful": False,
                "protected_actions": [],
                "recovery": None,
            }
        ],
        "publication": {"mode": "NONE"},
    }


def expect_error(manifest: dict, fragment: str) -> None:
    errors = validator.validate(manifest)
    if not any(fragment in error for error in errors):
        raise AssertionError(f"expected {fragment!r}; got {errors!r}")


def test_paths_and_publication() -> None:
    manifest = valid_manifest()
    manifest["task_list"]["target"] = "../../../tmp/todo.md"
    expect_error(manifest, "task_list.target")

    manifest = valid_manifest()
    manifest["increments"][0]["files"] = ["../../etc/passwd"]
    expect_error(manifest, "increments[0].files[0]")

    manifest = valid_manifest()
    manifest["publication"] = {
        "mode": "OPEN_PR",
        "branch": "task",
        "base_branch": "main",
        "commit_message": "change",
        "commit_paths": ["unrelated/secrets.env"],
        "pr_title": "change",
        "pr_body": "body",
        "protected_actions": [
            {"action": "commit verified candidate", "state": "AUTHORIZED", "owner": "user", "evidence_ref": "x"},
            {"action": "push task branch", "state": "AUTHORIZED", "owner": "user", "evidence_ref": "x"},
            {"action": "create pull request", "state": "AUTHORIZED", "owner": "user", "evidence_ref": "x"},
            {"action": "merge pull request", "state": "UNAUTHORIZED", "owner": "reviewer", "evidence_ref": "x"},
        ],
    }
    expect_error(manifest, "outside increment files")

    manifest = deepcopy(manifest)
    manifest["publication"]["commit_paths"] = ["src/app.py"]
    manifest["publication"]["protected_actions"][-1]["state"] = "AUTHORIZED"
    expect_error(manifest, "merge pull request must be UNAUTHORIZED")


def test_dependency_type_guard() -> None:
    """A non-string dependency must be a structured validator error, never a crash."""
    manifest = valid_manifest()
    manifest["increments"][0]["dependencies"] = [{"not": "a string"}]
    expect_error(manifest, "dependencies must contain only strings")


def test_nondeterministic_protocol_values() -> None:
    """A nondeterministic verifier must declare a usable bounded protocol."""
    invalid_protocols = (
        {"trials": 0, "accept_if": "accepted", "candidate_state": "stable", "stopping_rule": "stop"},
        {"trials": True, "accept_if": "accepted", "candidate_state": "stable", "stopping_rule": "stop"},
        {"trials": 1, "accept_if": "", "candidate_state": "stable", "stopping_rule": "stop"},
        {"trials": 1, "accept_if": "accepted", "candidate_state": "", "stopping_rule": "stop"},
        {"trials": 1, "accept_if": "accepted", "candidate_state": "stable", "stopping_rule": ""},
    )
    for protocol in invalid_protocols:
        manifest = valid_manifest()
        manifest["increments"][0]["verifier"] = {
            "reference": "test",
            "oracle": "detects violation",
            "class": "DECLARED_NONDETERMINISTIC",
            "protocol": protocol,
        }
        expect_error(manifest, "verifier.protocol")


def test_source_binding_field_required() -> None:
    manifest = valid_manifest()
    del manifest["source_binding"]["dirty_submodule_manifest_sha256"]
    expect_error(manifest, "source_binding missing field: dirty_submodule_manifest_sha256")


def test_exact_heading() -> None:
    manifest = valid_manifest()
    text = "PLAN_READY\n\n## Build manifest\n```json\n" + json.dumps(manifest) + "\n```\n\n### Build manifest checklist\ntext\n"
    extracted = validator.extract_manifest(text)
    if extracted != manifest:
        raise AssertionError("exact heading extraction changed manifest")


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_source_binding() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "base")
        (repo / "plans").mkdir()
        (repo / "plans" / "plan.md").write_text("one\n", encoding="utf-8")
        (repo / "untracked.txt").write_text("one\n", encoding="utf-8")

        first = source_binding.compute(repo, "plans/plan.md")
        (repo / "plans" / "plan.md").write_text("two\n", encoding="utf-8")
        second = source_binding.compute(repo, "plans/plan.md")
        if first != second:
            raise AssertionError("excluded plan path changed source binding")

        (repo / "untracked.txt").write_text("two\n", encoding="utf-8")
        third = source_binding.compute(repo, "plans/plan.md")
        if third["untracked_manifest_sha256"] == second["untracked_manifest_sha256"]:
            raise AssertionError("untracked content change did not change binding")

        os.chmod(repo / "untracked.txt", 0o755)
        fourth = source_binding.compute(repo, "plans/plan.md")
        if fourth["untracked_manifest_sha256"] == third["untracked_manifest_sha256"]:
            raise AssertionError("untracked mode change did not change binding")


def test_source_binding_config_independence() -> None:
    """Ambient Git configuration must not move any binding field."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "tracked.txt").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
        (repo / "caf\u00e9.txt").write_text("one\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        (repo / "tracked.txt").write_text("one\ntwo\nCHANGED\nfour\nfive\n", encoding="utf-8")
        (repo / "caf\u00e9.txt").write_text("two\n", encoding="utf-8")
        (repo / "plans").mkdir()
        (repo / "plans" / "plan.md").write_text("plan\n", encoding="utf-8")

        expected = source_binding.compute(repo, "plans/plan.md")
        hostile = (
            ("diff.context", "9"),
            ("core.quotePath", "false"),
            ("diff.algorithm", "histogram"),
            ("diff.indentHeuristic", "false"),
            ("diff.noprefix", "true"),
            ("core.autocrlf", "true"),
            ("diff.ignoreSubmodules", "all"),
        )
        for key, value in hostile:
            git(repo, "config", key, value)
        if source_binding.compute(repo, "plans/plan.md") != expected:
            raise AssertionError("ambient Git configuration changed the source binding")


def test_source_binding_nested_repository() -> None:
    """An untracked nested repository must bind by content instead of stopping the chain."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "base")
        (repo / "plans").mkdir()
        (repo / "plans" / "plan.md").write_text("plan\n", encoding="utf-8")

        nested = repo / "vendor" / "dep"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        git(nested, "config", "user.email", "test@example.com")
        git(nested, "config", "user.name", "Test")
        (nested / "lib.py").write_text("one\n", encoding="utf-8")

        first = source_binding.compute(repo, "plans/plan.md")

        (nested / "lib.py").write_text("two\n", encoding="utf-8")
        second = source_binding.compute(repo, "plans/plan.md")
        if first["untracked_manifest_sha256"] == second["untracked_manifest_sha256"]:
            raise AssertionError("nested repository content change did not change binding")

        git(nested, "add", "-A")
        git(nested, "commit", "-qm", "nested")
        third = source_binding.compute(repo, "plans/plan.md")
        if third["untracked_manifest_sha256"] != second["untracked_manifest_sha256"]:
            raise AssertionError("nested repository history leaked into the binding")


def test_source_binding_dirty_submodule() -> None:
    """Two different uncommitted submodule states must not bind identically."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inner = root / "inner"
        outer = root / "outer"
        inner.mkdir()
        outer.mkdir()
        git(inner, "init", "-q")
        git(inner, "config", "user.email", "test@example.com")
        git(inner, "config", "user.name", "Test")
        (inner / "f.txt").write_text("one\n", encoding="utf-8")
        git(inner, "add", "f.txt")
        git(inner, "commit", "-qm", "base")

        git(outer, "init", "-q")
        git(outer, "config", "user.email", "test@example.com")
        git(outer, "config", "user.name", "Test")
        git(outer, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
        git(outer, "commit", "-qm", "add submodule")
        (outer / "plans").mkdir()
        (outer / "plans" / "plan.md").write_text("plan\n", encoding="utf-8")

        clean = source_binding.compute(outer, "plans/plan.md")

        (outer / "sub" / "f.txt").write_text("two\n", encoding="utf-8")
        dirty_a = source_binding.compute(outer, "plans/plan.md")
        if dirty_a["dirty_submodule_manifest_sha256"] == clean["dirty_submodule_manifest_sha256"]:
            raise AssertionError("dirty submodule content did not change the binding")

        (outer / "sub" / "f.txt").write_text("three\n", encoding="utf-8")
        dirty_b = source_binding.compute(outer, "plans/plan.md")
        if dirty_b["dirty_submodule_manifest_sha256"] == dirty_a["dirty_submodule_manifest_sha256"]:
            raise AssertionError("two different dirty submodule states bound identically")

        # A committed submodule commit-pointer change is already visible in the
        # ordinary diff and must not also register as a dirty submodule.
        git(outer / "sub", "config", "user.email", "test@example.com")
        git(outer / "sub", "config", "user.name", "Test")
        git(outer / "sub", "add", "-A")
        git(outer / "sub", "commit", "-qm", "advance")
        git(outer, "add", "sub")
        advanced = source_binding.compute(outer, "plans/plan.md")
        if advanced["dirty_submodule_manifest_sha256"] != clean["dirty_submodule_manifest_sha256"]:
            raise AssertionError("a clean, committed submodule advance was misclassified as dirty")
        if advanced["staged_diff_sha256"] == clean["staged_diff_sha256"]:
            raise AssertionError("a committed submodule pointer advance did not appear in the staged diff")


def test_source_binding_invalid_utf8_filename() -> None:
    """An untracked file with invalid-UTF-8 bytes in its name must not crash the binding."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "base")
        (repo / "plans").mkdir()
        (repo / "plans" / "plan.md").write_text("plan\n", encoding="utf-8")

        (repo / os.fsdecode(b"bad-\xff.txt")).write_bytes(b"one")
        first = source_binding.compute(repo, "plans/plan.md")

        os.remove(repo / os.fsdecode(b"bad-\xff.txt"))
        (repo / os.fsdecode(b"bad-\xfe.txt")).write_bytes(b"one")
        second = source_binding.compute(repo, "plans/plan.md")

        if first["untracked_manifest_sha256"] == second["untracked_manifest_sha256"]:
            raise AssertionError("distinct invalid-UTF-8 filenames bound identically")


def test_source_binding_nested_invalid_utf8_filename() -> None:
    """Invalid-UTF-8 names inside nested repositories must sort without crashing."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "base")
        (repo / "plans").mkdir()
        (repo / "plans" / "plan.md").write_text("plan\n", encoding="utf-8")

        nested = repo / "vendor" / "dep"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        (nested / os.fsdecode(b"bad-\xff.txt")).write_bytes(b"one")
        source_binding.compute(repo, "plans/plan.md")


def main() -> int:
    test_paths_and_publication()
    test_dependency_type_guard()
    test_nondeterministic_protocol_values()
    test_source_binding_field_required()
    test_exact_heading()
    test_source_binding()
    test_source_binding_config_independence()
    test_source_binding_nested_repository()
    test_source_binding_dirty_submodule()
    test_source_binding_invalid_utf8_filename()
    test_source_binding_nested_invalid_utf8_filename()
    print("build-agent contract regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
