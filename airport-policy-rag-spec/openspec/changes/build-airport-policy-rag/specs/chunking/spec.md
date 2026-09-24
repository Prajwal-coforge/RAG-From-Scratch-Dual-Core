# chunking capability

## ADDED Requirements

### Requirement: CHK-01 Preserve policy structure
The system SHALL create source-linked child passages that preserve section scope, table labels, and rule dependencies.

#### Scenario: Long policy section
- **GIVEN** a long section containing a rule and a linked exception
- **WHEN** the section is split
- **THEN** children retain headings, source spans, parent links, and a path to the exception.

### Requirement: CHK-02 Enforce hard boundaries
The system SHALL prevent chunks and overlap from crossing source versions or permission boundaries.

#### Scenario: Restricted neighboring section
- **GIVEN** adjacent internal and restricted policy sections
- **WHEN** chunking runs
- **THEN** no child contains content from both access scopes.

### Requirement: CHK-03 Detect model input overflow
The system SHALL detect and explicitly handle over-limit embedding and reranker inputs.

#### Scenario: Different tokenizers
- **GIVEN** a child that fits the embedding tokenizer but exceeds the reranker's paired input limit
- **WHEN** it is prepared for reranking
- **THEN** the passage is split into traceable windows and no hidden truncation loses policy text.
