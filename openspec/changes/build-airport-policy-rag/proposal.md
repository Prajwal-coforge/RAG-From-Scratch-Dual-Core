# Airport Policy RAG

## Why
Build a rubric-complete local policy assistant that demonstrates traceable retrieval and source-quality diagnosis.

## What Changes
- Add curated aviation and generated airport-policy corpora.
- Add local ingestion, chunking, embeddings, vector/keyword/graph retrieval, and cross-encoder reranking.
- Add bounded agents, cited answers, a JavaScript interface, evaluation, and CI evidence.
- Exclude data lake infrastructure and hosted inference.
- Exclude a data governance layer: no authentication, user roles, or document access control.

## Capabilities

### New Capabilities
- corpus: Requirements defined in specs/corpus/spec.md.
- ingestion: Requirements defined in specs/ingestion/spec.md.
- chunking: Requirements defined in specs/chunking/spec.md.
- embeddings: Requirements defined in specs/embeddings/spec.md.
- retrieval: Requirements defined in specs/retrieval/spec.md.
- answering: Requirements defined in specs/answering/spec.md.
- agents: Requirements defined in specs/agents/spec.md.
- interface: Requirements defined in specs/interface/spec.md.
- evaluation: Requirements defined in specs/evaluation/spec.md.

### Modified Capabilities
None; this is a proposed initial implementation.

## Impact
New local backend, frontend, model integrations, graph store, test harness, and documentation. Implementation details and approved tradeoffs are in design.md and PROJECT_SPEC.md.
