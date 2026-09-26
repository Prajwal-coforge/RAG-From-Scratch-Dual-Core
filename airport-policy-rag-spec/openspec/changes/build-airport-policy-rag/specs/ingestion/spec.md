# ingestion capability

## ADDED Requirements

### Requirement: ING-01 Traceable source coverage
The system SHALL preserve traceability from every indexed passage to an original document version and source span.

#### Scenario: Source normalization
- **GIVEN** policy text containing numbered sections and unusual whitespace
- **WHEN** it is normalized and indexed
- **THEN** every citation resolves to the corresponding original source span.

### Requirement: ING-02 Atomic publication
The system SHALL serve only complete validated index generations and support idempotent ingestion.

#### Scenario: Interrupted ingestion
- **GIVEN** an active complete index and a new partially built index
- **WHEN** embedding fails before publication
- **THEN** the previous generation remains available and partial results are not exposed.

### Requirement: ING-03 Quality metadata validation
The system SHALL flag unresolved references, conflicting active versions, and missing required metadata before publication.

#### Scenario: Missing version metadata
- **GIVEN** a document with no version or source hash
- **WHEN** ordinary ingestion is requested
- **THEN** publication is refused with a quality finding.
