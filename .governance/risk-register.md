# Risk Register

### RISK-001: Skill provenance or contract tampering
- **Category**: OWASP AST01 Malicious Skills
- **Likelihood**: medium
- **Impact**: high
- **Mitigation**: Treat supplied skill bundles as integrity-sensitive; require explicit provenance and narrow path scope for replacements.
- **Residual risk**: An apparently trusted upstream bundle can still contain unsafe instructions.
- **Owner**: Repository maintainer

### RISK-002: Dependency or marketplace supply-chain compromise
- **Category**: OWASP AST02 / NIST GAI-12
- **Likelihood**: medium
- **Impact**: high
- **Mitigation**: Review new dependencies, preserve immutable identities when available, validate manifests, and record provenance.
- **Residual risk**: Upstream systems or distribution channels can be compromised after review.
- **Owner**: Repository maintainer

### RISK-003: Agent authority escalation
- **Category**: OWASP AST03 Over-Privileged Skills
- **Likelihood**: medium
- **Impact**: high
- **Mitigation**: Keep Scout read-only; require exact `PLAN_READY` approval before Build; require separate merge authorization.
- **Residual risk**: Tool configuration outside the repository may still grant excessive permissions.
- **Owner**: Repository maintainer

### RISK-004: Prompt injection through repository or external content
- **Category**: OWASP AST05 Untrusted External Instructions
- **Likelihood**: high
- **Impact**: high
- **Mitigation**: Treat evidence and external content as untrusted data and resolve authority through explicit governance.
- **Residual risk**: Ambiguous human instructions can still create authority conflicts.
- **Owner**: Repository maintainer

### RISK-005: Weak isolation across skill bundles
- **Category**: OWASP AST06 Weak Isolation
- **Likelihood**: medium
- **Impact**: medium
- **Mitigation**: Scope bundle updates to one authorized `skills/<name>/` path and reject neighboring drift.
- **Residual risk**: Shared plugin metadata can still affect all bundled skills.
- **Owner**: Repository maintainer

### RISK-006: Governance drift from plugin behavior
- **Category**: OWASP AST07 Update Drift / AST09 No Governance
- **Likelihood**: medium
- **Impact**: high
- **Mitigation**: Keep workflow semantics synchronized across README, manifests, governance, and supplied skill contracts; verify cross-references.
- **Residual risk**: External skill updates can change behavior without corresponding governance updates.
- **Owner**: Repository maintainer

### RISK-007: Confident but incorrect packaging or documentation
- **Category**: NIST GAI-2 Confabulation / GAI-8 Information Integrity
- **Likelihood**: medium
- **Impact**: medium
- **Mitigation**: Require evidence-grounded claims, JSON validation, path checks, and current-state verification before completion.
- **Residual risk**: Structural checks cannot prove all runtime plugin behavior.
- **Owner**: Repository maintainer

### RISK-008: Secret or private-data exposure
- **Category**: NIST GAI-4 Data Privacy / GAI-9 Information Security
- **Likelihood**: low
- **Impact**: high
- **Mitigation**: Prohibit hardcoded or logged credentials and stop on discovered exposure.
- **Residual risk**: Secrets may exist outside tracked repository content.
- **Owner**: Repository maintainer

### RISK-009: Approval-boundary bypass
- **Category**: NIST Human-AI Configuration / OWASP AST03
- **Likelihood**: medium
- **Impact**: high
- **Mitigation**: Preserve human approval of the exact `PLAN_READY` identity and prohibit agent self-approval or implicit Build authorization.
- **Residual risk**: External orchestration may misrepresent approval state.
- **Owner**: Repository maintainer

## Assumptions
- The current highest-impact risks are agent authority, skill provenance, package integrity, and approval-gate bypass.
- The repository has no production runtime or user-data store today.
