# Increment execution gates

Run these gates in order for each increment.
Do not skip a gate because a later gate succeeds.

## G0: Expected-state gate

Compare the current repository state with the previous expected-state checkpoint.
Stop before mutation when external or unrelated state changed.

## G1: Scope and authority gate

Confirm that the increment action is inside declared scope.
Confirm that every target file is declared.
Confirm that every protected or destructive action has explicit authority before Apply.

## G2: Evaluation gate

Confirm that each obligation has a meaningful oracle.
Confirm that declared failure partitions and boundary cases have direct evidence.
For defect work, establish the regression signal before the fix when reproducible.
For refactoring, establish behavior evidence before the structural change.
If behavior crosses an owned boundary, require the plan-declared boundary contract verifier.

## G3: Construction gate

Apply only the current increment.
Inspect the actual result after each action with a dependent successor.
Require the declared postcondition before the successor starts.

## G4: Engineering gate

Run the repository-declared construction checks that apply to the delta.
Examples include compilation, type checks, lint, static analysis, schema checks, or engineering-rule checks.
Do not invent a command that the repository or plan does not declare.

Scope repair to the increment delta.
Do not repair unrelated working-tree findings.

## G5: Verifier safety gate

Inspect the complete executable verifier path before execution.
Include wrappers, runner configuration, plugins, hooks, fixtures, loaded test code, child processes, and network access.

When safety cannot be established at bounded cost, stop before running the verifier.
Do not execute a verifier to discover whether it is safe.

## G6: Behavior verification gate

Run the plan-declared verifier within its command and increment budgets.

For a `DETERMINISTIC` verifier, perform the declared same-state stability check.
The candidate state must not change between the compared runs.

For a `DECLARED_NONDETERMINISTIC` verifier, run the exact plan protocol.
Keep the candidate state unchanged for all trials unless the protocol explicitly states otherwise.

Do not reinterpret a failing oracle as acceptable.
Do not change the verifier to make the candidate succeed.

## G7: Minimality and trace gate

Inspect the final increment diff.
Map every changed line to an authorized obligation.
Reject speculative behavior and single-use abstractions.
Reject adjacent cleanup.

Remove only orphans created by this increment.
Mention pre-existing dead code without changing it.

## G8: Vertical closure gate

Run the final increment verification on the final candidate state.
Confirm that the whole vertical slice is in a valid state.
Record the resulting expected-state checkpoint.

For a stateful partial failure, execute the plan-declared whole-increment recovery.
Verify that recovery restored the declared pre-increment state.
If recovery fails, stop and report that failure.

## Repair loop

Use only the repair budget declared by Plan or current governance.
Each repair must respond to observed evidence.

If a repair gives no new evidence or progress, do not repeat it mechanically.
Stop when the declared budget or stopping rule is reached.
