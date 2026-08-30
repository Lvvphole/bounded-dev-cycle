# Build manifest

Plan must include one machine-readable Build manifest in each `PLAN_READY` artifact.
The manifest is the executable handoff contract between Plan and Build Agent.

Place it under the exact heading `## Build manifest`.
Use one fenced `json` block.

```json
{
  "schema": "build-agent/v2",
  "completion_authority": "named authority",
  "source_binding": {
    "commit": "git commit identity",
    "staged_diff_sha256": "sha256",
    "unstaged_diff_sha256": "sha256",
    "untracked_manifest_sha256": "sha256",
    "dirty_submodule_manifest_sha256": "sha256",
    "excluded_plan_path": "path/to/plan.md"
  },
  "task_list": {
    "target": "tasks/todo.md",
    "preservation_evidence": "repository evidence that unrelated content is preserved",
    "entries": [
      {
        "increment": "INC-1",
        "text": "one task-list entry"
      }
    ]
  },
  "increments": [
    {
      "id": "INC-1",
      "objective": "one observable vertical outcome",
      "obligations": ["OBL-1"],
      "dependencies": [],
      "files": ["path/to/file"],
      "actions": [
        {
          "instruction": "authorized construction action",
          "postcondition": "observable result required before a dependent action"
        }
      ],
      "acceptance_criteria": ["observable criterion"],
      "verifier": {
        "reference": "repository command or verifier id",
        "oracle": "observable result that can detect violation",
        "class": "DETERMINISTIC"
      },
      "budgets": {
        "repair_attempts": 3,
        "command_timeout_seconds": 120,
        "increment_timeout_seconds": 600
      },
      "checkpoint": "expected repository state after closure",
      "stateful": false,
      "protected_actions": [],
      "recovery": null
    }
  ],
  "publication": {
    "mode": "NONE"
  }
}
```

The numeric values are examples only.
Plan or repository governance must select actual budgets.
Build Agent must not copy example values as defaults.

## Canonical source binding

Plan and Build must use the bundled script. Do not reconstruct the projection independently.

```bash
python scripts/source-binding.py --repo <repo> --exclude-plan-path <repository-relative-plan-path>
```

The script hashes the Git `HEAD`, canonical staged and unstaged binary diffs, and a canonical untracked-file manifest.
The untracked manifest sorts paths bytewise and binds each path, file type, permission mode, and content or symlink-target SHA-256.
The excluded plan path must be repository-relative and cannot contain `..`.

For `DECLARED_NONDETERMINISTIC`, add this verifier field:

```json
"protocol": {
  "trials": 5,
  "accept_if": "at least 3 clean trials",
  "candidate_state": "unchanged across all trials",
  "stopping_rule": "run exactly 5 trials"
}
```

Use only values selected by Plan or current governance.

For a protected action, use this shape:

```json
{
  "action": "database migration",
  "state": "APPROVAL_GATED",
  "owner": "named approval owner",
  "evidence_ref": "approval or authority reference"
}
```

Allowed states are `AUTHORIZED`, `APPROVAL_GATED`, and `UNAUTHORIZED`.
Build must resolve the state before Apply.

Stateful increments must replace `recovery: null` with an object that contains `reference` and `oracle`.

## Open pull request publication

Use `publication.mode: "OPEN_PR"` only when the frozen outcome requires an open pull request.
Plan must supply all values so Build does not invent publication details.

```json
{
  "mode": "OPEN_PR",
  "branch": "task-branch-name",
  "base_branch": "main",
  "commit_message": "task-scoped commit message",
  "commit_paths": ["path/authorized/by/plan"],
  "pr_title": "task-scoped pull request title",
  "pr_body": "task-scoped pull request body",
  "protected_actions": [
    {
      "action": "commit verified candidate",
      "state": "AUTHORIZED",
      "owner": "user",
      "evidence_ref": "task authority"
    },
    {
      "action": "push task branch",
      "state": "AUTHORIZED",
      "owner": "user",
      "evidence_ref": "task authority"
    },
    {
      "action": "create pull request",
      "state": "AUTHORIZED",
      "owner": "user",
      "evidence_ref": "task authority"
    },
    {
      "action": "merge pull request",
      "state": "UNAUTHORIZED",
      "owner": "repository reviewer",
      "evidence_ref": "non-goal"
    }
  ]
}
```

Every increment file, `task_list.target`, `source_binding.excluded_plan_path`, and `publication.commit_paths` entry must be a repository-relative path without `..`.
`publication.commit_paths` must be a subset of the union of all increment `files`.
Do not include unrelated dirty files.
`merge pull request` must be `UNAUTHORIZED` in every `OPEN_PR` manifest.
Opening a pull request does not authorize merge or deployment.
