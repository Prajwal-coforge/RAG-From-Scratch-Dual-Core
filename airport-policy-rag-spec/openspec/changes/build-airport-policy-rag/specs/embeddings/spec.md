# embeddings capability

## ADDED Requirements

### Requirement: EMB-01 Compatible query and document vectors
The system SHALL use a consistent pinned embedding configuration for indexing and querying.

#### Scenario: Model mismatch
- **GIVEN** an index built under one embedding model digest
- **WHEN** a query requests a different configuration
- **THEN** retrieval is refused until a compatible index is selected.

#### Scenario: Input over the embedding limit
- **GIVEN** a formatted input longer than the embedding model's maximum sequence length
- **WHEN** it is submitted through sentence-transformers, which would truncate it silently
- **THEN** the input is refused before encoding and reported, not embedded in truncated form.

### Requirement: EMB-02 Real vector persistence and retrieval
The system SHALL demonstrate a real two-text vector-store retrieval loop before full corpus ingestion.

#### Scenario: Minimal retrieval proof
- **GIVEN** two semantically distinct short texts stored in the selected vector store
- **WHEN** a question clearly about one text is embedded and searched
- **THEN** the relevant text is returned and actual terminal output is retained.

### Requirement: EMB-03 Safe index refresh
The system SHALL create a new compatible generation when model or input formatting changes.

#### Scenario: Embedding configuration update
- **GIVEN** a published index and changed document formatting
- **WHEN** reindexing is performed
- **THEN** queries continue using the old matching configuration until the new complete generation is published.
