# Airport Policy RAG — specification handoff

Start with START_HERE.md. PROJECT_SPEC.md is the complete standalone specification. The OpenSpec change provides 39 proposed requirements with acceptance scenarios and a milestone task list. No application has been implemented or tested by this package.

## Contents

- PROJECT_SPEC.md — product requirements, architecture, security, data contracts, algorithms, evaluation, CI, and submission evidence.
- START_HERE.md — instructions and a kickoff prompt for the work-laptop development agent.
- openspec/changes/build-airport-policy-rag — proposal, design snapshot, tasks, and 10 capability specs.
- config — pinned aviation sources, model/retrieval defaults, synthetic organization, and access-policy examples.
- ORIGINAL_ASSIGNMENT.txt — original user-supplied assignment for traceability.
- RUBRIC_TRACEABILITY.csv — all 100 rubric points mapped to planned tests and evidence.
- REQUIREMENTS.csv — requirement inventory.
- VALIDATION.md — package checks, not application test results.

## Important boundaries

No data lake. DGS is required. Local model inference only. Imported airline examples retain their issuer context. Four generated airport-policy documents remain required for the rubric. The technology substitutions are user-selected, not represented as instructor-approved.

The design.md is a snapshot of PROJECT_SPEC.md for the initial OpenSpec change; when revising the design, update the master handoff or record which later change supersedes it. Do not treat planned capabilities as implemented.

The package contains specifications and configuration examples; no third-party source code or model weights are bundled. Fetch only the pinned allowlisted corpus files during implementation and retain their license.
