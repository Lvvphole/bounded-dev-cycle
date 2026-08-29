# Style Policy

## Language-specific rules
- Treat Markdown and JSON as the repository's current governed text formats.
- Keep JSON standards-compliant with double-quoted keys and no comments.
- Keep Markdown compatible with common GitHub rendering.

## Formatting
- Use short headings and compact bullets.
- Use fenced code blocks only for literal commands, schemas, or workflow diagrams.
- Keep one logical rule per bullet.
- Avoid whitespace-only or formatting-only churn outside task scope.
- Preserve final newline characters.

## Naming conventions
- Preserve canonical skill directory names: `scout-agent`, `plan`, and `build-agent`.
- Preserve canonical workflow states exactly: `PLAN_READY`, `BUILD_READY`, `BUILD_HALTED`, `BUILD_REFUSED`.
- Use lowercase kebab-case for new governance filenames unless a standard filename is required.
- Use stable risk identifiers in the form `RISK-NNN`.

## Patterns to follow
- Route global instructions through `AGENTS.md`.
- Route task-specific context through `CONTEXT.md`.
- Keep `CLAUDE.md` limited to identity and pointers.
- Extend policy in `.governance/` instead of bloating `AGENTS.md`.
- Keep Scout read-only and keep Plan/Build execution boundaries explicit.
- Prefer minimum-scope diffs and verifiable claims.

## Patterns to avoid
- Do not duplicate full policies across governance files.
- Do not rewrite supplied skills merely to normalize prose or formatting.
- Do not invent build systems, package managers, tests, services, or dependencies.
- Do not use ambiguous authority language such as “as needed” for destructive or privileged actions.
- Do not collapse human approval into an agent self-approval step.

## Assumptions
- No additional language-specific formatter or linter is currently authoritative.
- Existing supplied skill formatting takes precedence inside immutable skill bundles.
