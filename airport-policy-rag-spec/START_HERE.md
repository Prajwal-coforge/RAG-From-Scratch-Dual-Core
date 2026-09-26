# Start here — instructions for the development agent

You are implementing the project described in PROJECT_SPEC.md on the user's work laptop. This is a specification handoff, not an implemented app.

1. Read PROJECT_SPEC.md, ORIGINAL_ASSIGNMENT.txt, config/model-and-retrieval-defaults.json, and the proposed OpenSpec change. Follow local repository instructions and preserve unrelated work.
2. Treat the user's selected Memgraph/Ollama stack, removal of the data lake, and removal of the data governance layer (no authentication, roles, or document access control) as project decisions. Record the assignment's stack wording as an explicit substitution; do not silently reintroduce Chroma or cloud inference.
3. Assume the selected “airport corpus” refers to the three pinned aviation files from DecisionsDev/policy-corpus. Use the exact file links and folder exclusions in PROJECT_SPEC.md section 3 and the raw URLs/checksums in config/corpus-manifest.json. Keep their issuers separate. Build the generated airport-policy set as required by the lab.
4. Inspect the target workspace and runtime capabilities. Initialize a project-local OpenSpec workflow using the currently supported CLI. Preserve these proposed requirements. Do not archive the change or claim current capabilities exist yet.
5. Implement tasks in milestone order. First produce and save an actual two-text embedding, Memgraph storage, and retrieval demonstration before full corpus ingestion.
6. Use original policy files as authoritative evidence. Keep evaluation labels, reference code, source-generation prompts, and expected answers outside the index.
7. Add real tests and recorded evidence with each capability. Run local and CI evaluation with actual services. Never invent results or mark skipped model tests as a passing full pipeline.
8. Make ordinary engineering decisions autonomously and record them. Ask only about a real blocker such as unavailable credentials, hardware restrictions, or an unknown target workspace. Do not deploy publicly or send policy data to hosted models.
9. Keep OpenSpec tasks and the rubric traceability file current. Finish with working code, accurate run instructions, actual evaluation results, a source-defect diagnosis, and the ordered submission PDF.

Read order: PROJECT_SPEC.md → proposed change/specs → tasks.md → source/config manifests → original assignment.

The JSON configuration files are implementation defaults, not preexisting application code. The checksums pin imported files; generated policies and tests must be created and verified during implementation.

## Copyable kickoff prompt

Read START_HERE.md and PROJECT_SPEC.md in this handoff. Implement the Airport Policy RAG project in the current workspace using the included proposed OpenSpec change. Start with environment preflight and the actual two-text Memgraph/Ollama retrieval proof, then follow the milestone checklist. Exclude the data lake and the data governance layer, preserve aviation issuer boundaries, and satisfy the generated-corpus and evidence requirements. Use local models only. Record decisions and real test results; do not claim completion until the live evaluation and submission evidence are complete.
