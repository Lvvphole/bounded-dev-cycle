#!/usr/bin/env python3
"""Verify the bug-fix route and verification contract with hash-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "bounded-dev-cycle/bug-fix-governance-regression/v1"
REQUIRED_FILES = ("CONTEXT.md", ".governance/testing.md")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def section(text: str, start: str, next_prefix: str) -> str:
    marker = f"{start}\n"
    begin = text.find(marker)
    if begin < 0:
        return ""
    begin += len(marker)
    end = text.find(f"\n{next_prefix}", begin)
    return text[begin:] if end < 0 else text[begin:end]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--previous-evidence-sha256")
    args = parser.parse_args()

    previous = args.previous_evidence_sha256
    if previous is not None and not HEX64.fullmatch(previous):
        raise SystemExit("previous evidence SHA-256 must be 64 lowercase hex characters")

    root = Path(args.repo).resolve()
    raw: dict[str, bytes] = {}
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"required file missing: {relative}")
        raw[relative] = path.read_bytes()

    context = raw["CONTEXT.md"].decode("utf-8")
    testing = raw[".governance/testing.md"].decode("utf-8")
    route = section(context, "## Task: bug-fix", "## Task:")
    contract = section(testing, "### bug-fix", "### ")

    checks = [
        {
            "id": "route-present",
            "pass": bool(route),
        },
        {
            "id": "removal-first",
            "pass": "BUGFIX-REMOVE-FIRST" in route,
        },
        {
            "id": "no-invented-files",
            "pass": "BUGFIX-NO-INVENTED-FILES" in route,
        },
        {
            "id": "verification-contract-present",
            "pass": bool(contract),
        },
        {
            "id": "regression-set-defined",
            "pass": "BUGFIX-REGRESSION-SET" in contract,
        },
        {
            "id": "complete-pass-criterion",
            "pass": "BUGFIX-PASS" in contract,
        },
        {
            "id": "sha256-evidence-chain",
            "pass": "BUGFIX-EVIDENCE-CHAIN" in contract,
        },
    ]

    inputs = {
        path: {
            "sha256": sha256(content),
            "size": len(content),
        }
        for path, content in sorted(raw.items())
    }
    state_sha256 = sha256(canonical_json(inputs))
    status = "PASS" if all(item["pass"] for item in checks) else "FAIL"
    evidence = {
        "checks": checks,
        "inputs": inputs,
        "oracle_sha256": sha256(Path(__file__).read_bytes()),
        "previous_evidence_sha256": previous,
        "schema": SCHEMA,
        "state_sha256": state_sha256,
        "status": status,
    }
    evidence_sha256 = sha256(canonical_json(evidence))
    output = {**evidence, "evidence_sha256": evidence_sha256}
    print(canonical_json(output).decode("ascii"))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
