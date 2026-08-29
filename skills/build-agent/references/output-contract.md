# Build output contract

Use structured records only for Build dispositions.
Do not add a free-form completion claim to terminal records.

## BUILD_REFUSED

```json
{
  "disposition": "BUILD_REFUSED",
  "condition": "non-PLAN_READY input",
  "evidence": ["reference to observed input disposition"]
}
```

## BUILD_HALTED

```json
{
  "disposition": "BUILD_HALTED",
  "increment": "INC-N or null",
  "condition": "specific blocking condition",
  "evidence": ["observable evidence references"],
  "recovery": {
    "required": false,
    "operation": null,
    "exit_code": null,
    "state_check": null
  },
  "resolution_owner": "Plan, human authority, repository owner, or verifier owner"
}
```

When recovery ran, record the real operation, exit code, and restored-state evidence.

## BUILD_INCREMENT_READY

This record reports evidence for one closed increment.
It is not a release or acceptance verdict.

```json
{
  "disposition": "BUILD_INCREMENT_READY",
  "increment": "INC-N",
  "obligations": ["OBL-N"],
  "files_touched": ["path"],
  "verification": [
    {
      "verifier": "declared verifier reference",
      "class": "DETERMINISTIC or DECLARED_NONDETERMINISTIC",
      "result_code": 0,
      "oracle": "observed oracle result",
      "evidence_ref": "path or transcript reference"
    }
  ],
  "checkpoint_ref": "expected-state reference",
  "provenance_ref": "ordered execution evidence reference"
}
```

## BUILD_READY

Use only after every declared increment closes, final Definition-of-Done verification runs, and any authorized `OPEN_PR` publication completes.
This record transfers evidence to the plan's completion authority.

```json
{
  "disposition": "BUILD_READY",
  "completion_authority": "verbatim value from PLAN_READY",
  "increments": [
    {
      "increment": "INC-N",
      "obligations": ["OBL-N"],
      "gate_evidence_ref": "reference",
      "verifier_evidence_ref": "reference"
    }
  ],
  "publication": {
    "mode": "NONE or OPEN_PR",
    "commit_sha": null,
    "branch": null,
    "pull_request_ref": null,
    "pull_request_state": null
  },
  "provenance_ref": "complete ordered execution evidence reference"
}
```

For `OPEN_PR`, replace null publication values with observed evidence.
The pull request state must be `OPEN` when Build reports `BUILD_READY` for an open-PR outcome.

## Provenance

Record observable execution evidence in order.
For each subprocess, record command text, exit code, and a concise result summary.
Record relevant repository checkpoints and file writes.
Record the plan identity, source-state identity, active skill identity, engineering-rule identity, verifier references, declared budgets, task-list write, and publication evidence when available.
Do not invent unavailable runtime identity fields.
