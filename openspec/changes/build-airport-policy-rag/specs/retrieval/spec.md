# retrieval capability

## ADDED Requirements

### Requirement: RET-01 Explicit retrieval modes
The system SHALL provide independently executable vector, hybrid, reranked, graph-assisted, and agentic modes with recorded mode identity.

#### Scenario: Baseline comparison
- **GIVEN** a fixed corpus, question, principal, and generation settings
- **WHEN** vector and hybrid modes run
- **THEN** the report isolates candidate-retrieval differences without changing the source or user permissions.

### Requirement: RET-02 Hybrid candidate merging
The system SHALL combine semantic and keyword candidates using a documented rank-combination and deduplication rule.

#### Scenario: Exact section identifier
- **GIVEN** a query containing a policy identifier
- **WHEN** hybrid search runs
- **THEN** keyword and vector contributions remain observable and repeated chunks appear once.

### Requirement: RET-03 Authorized candidate recall
The system SHALL retrieve relevant permitted passages even when forbidden passages have higher similarity.

#### Scenario: Forbidden nearest neighbors
- **GIVEN** many restricted close matches and one relevant permitted passage
- **WHEN** authorized vector search runs
- **THEN** the permitted passage remains eligible for the requested result count.

### Requirement: RET-04 Independent reranking
The system SHALL explicitly rescore question-passage pairs after initial retrieval and retain before/after ordering.

#### Scenario: Reranker invocation
- **GIVEN** a nonempty candidate set
- **WHEN** reranked retrieval runs
- **THEN** actual pair scores and ranking changes are recorded without representing scores as truth probabilities.

### Requirement: RET-05 Verified graph evidence
The system SHALL expand only validated, scoped policy relationships within configured limits.

#### Scenario: Cross-policy lookup
- **GIVEN** a policy clause referencing another authorized policy
- **WHEN** graph-assisted retrieval runs
- **THEN** the referenced clause can enter the candidate set with its supporting path and source provenance.
