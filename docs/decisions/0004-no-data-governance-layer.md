# 0004 — No data governance layer

Status: accepted for this project. Not instructor approval.
Date: 2026-09-25

The handoff specified a Data Governance Service (DGS): server-side identities, roles, an organization chart, per-document and per-section access rules, deny precedence, revocation handling, and audit records, with local login and sessions to identify the user. The project drops that layer and the authentication that served it.

The assignment's rubric does not ask for access control. None of its 100 points depend on it, and the layer would have touched every retrieval, graph, citation, agent, and UI path.

What is removed from the handoff and the OpenSpec change:

- The `governance` capability, DGS-01 to DGS-06, and RET-03 "Authorized candidate recall".
- PROJECT_SPEC.md sections "DGS access model" and "Authentication", the login screen and auth endpoints, and the restricted governance screen.
- `config/access-policy-examples.json` and `config/organization-seed.json`.
- The restricted supervisor section planned for AP-SEC-003, the manager-only evaluation case, the unauthorized-disclosure metric, and the access-control cases in the failure suite.

What stays, because it is data quality and correctness rather than access control:

- Source hashes, provenance, version and effective-date metadata, SUPERSEDES edges, and the clean, duplicate, dirty-stale, and historical manifests. The planted-defect diagnosis (15 points) depends on them.
- Issuer and corpus separation. SkyWings rules still do not apply to AetherSky staff.
- Prompt-injection isolation, allowlisted agent tools, and parameterized Cypher.

The application serves one local user, and every indexed policy is readable. Role, Department, and Control graph nodes stay as policy concepts named in the sources.

The chunker no longer carries an `access_policy_id`. Children split at document versions and parent sections only. `config/corpus-manifest.json` no longer has `tenant_id`, `classification`, or `access_policy_id`.
