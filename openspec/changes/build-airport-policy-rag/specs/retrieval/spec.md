# retrieval capability

## ADDED Requirements

### Requirement: RET-01 Explicit retrieval modes
The system SHALL provide independently executable vector, hybrid, reranked, graph-assisted, and agentic modes with recorded mode identity.

#### Scenario: Baseline comparison
- **GIVEN** a fixed corpus, question, and generation settings
- **WHEN** vector and hybrid modes run
- **THEN** the report isolates candidate-retrieval differences without changing the source or generation settings.

### Requirement: RET-02 Hybrid candidate merging
The system SHALL combine semantic candidates with locally implemented BM25 keyword candidates using reciprocal rank fusion and a documented deduplication rule.

#### Scenario: Exact section identifier
- **GIVEN** a query containing a policy identifier
- **WHEN** hybrid search runs
- **THEN** keyword and vector contributions remain observable and repeated chunks appear once.

#### Scenario: Identifier tokens survive keyword indexing
- **GIVEN** chunk text containing AP-BAG-001, section 4.2, and 23 kg
- **WHEN** the BM25 index is built and queried for those terms
- **THEN** each is matched as a single term and its BM25 score, exact-match boost, and rank are recorded.

### Requirement: RET-04 Independent reranking
The system SHALL explicitly rescore question-passage pairs after initial retrieval and retain before/after ordering.

#### Scenario: Reranker invocation
- **GIVEN** a nonempty candidate set
- **WHEN** reranked retrieval runs
- **THEN** actual pair scores and ranking changes are recorded without representing scores as truth probabilities.

### Requirement: RET-05 Verified graph evidence
The system SHALL expand only validated, scoped policy relationships within configured limits.

#### Scenario: Cross-policy lookup
- **GIVEN** a policy clause referencing another policy in the same corpus
- **WHEN** graph-assisted retrieval runs
- **THEN** the referenced clause can enter the candidate set with its supporting path and source provenance.
