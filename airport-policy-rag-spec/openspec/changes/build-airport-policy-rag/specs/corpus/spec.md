# corpus capability

## ADDED Requirements

### Requirement: COR-01 Pinned imported aviation sources
The system SHALL ingest only allowlisted aviation source files with verified provenance and maintain issuer-specific corpus boundaries.

#### Scenario: Imported file matches manifest
- **GIVEN** a source file with the expected hash and issuer
- **WHEN** the file is imported
- **THEN** its provenance is retained and it is searchable only under the corresponding corpus context.

### Requirement: COR-02 Genuine generated lab corpus
The project SHALL include four locally LLM-generated policy documents, each 500–800 prose words, including an intentionally obsolete duplicate.

#### Scenario: Generated source evidence
- **GIVEN** four generated policy files and generation records
- **WHEN** the source audit runs
- **THEN** word counts, model records, source identities, and the planted conflict are reported without treating imported documents as generated.

### Requirement: COR-03 Separated evaluation fixtures
The system SHALL preserve clean, duplicate, and stale-source fixtures without modifying original evidence.

#### Scenario: Stale source reproduction
- **GIVEN** a deliberately stale source delivery and a clean delivery
- **WHEN** the same diagnostic question is run against both
- **THEN** the report records the source difference, retrieved clauses, actual answers, and any retrieval or generation contribution to the failure.
