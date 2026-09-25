# answering capability

## ADDED Requirements

### Requirement: ANS-01 Grounded attributed answers
The system SHALL produce answers using supplied evidence and resolvable document/section citations.

#### Scenario: Supported answer
- **GIVEN** evidence containing the required rule
- **WHEN** the local generation API answers a question
- **THEN** the answer identifies its supporting document and section and all citation IDs resolve.

### Requirement: ANS-02 Missing-information handling
The system SHALL report missing evidence or request clarification instead of inventing absent policy details.

#### Scenario: Missing base-rate table
- **GIVEN** a compensation policy with no base hourly rate
- **WHEN** the user asks for exact base pay
- **THEN** the response identifies insufficient evidence and does not fabricate a rate.

### Requirement: ANS-03 Conflict visibility
The system SHALL surface unresolved conflicting sources instead of silently choosing by semantic score.

#### Scenario: Conflicting active versions
- **GIVEN** two applicable sources with incompatible rules and no authoritative precedence
- **WHEN** an affected question is asked
- **THEN** the response identifies the conflict with citations to both sources.

### Requirement: ANS-04 Source instruction isolation
The system SHALL treat retrieved text as evidence rather than authority over tools or system behavior.

#### Scenario: Malicious policy text
- **GIVEN** an indexed passage that instructs the assistant to call a tool or ignore its rules
- **WHEN** it is retrieved
- **THEN** it is treated as evidence only and no unapproved tool is invoked.

### Requirement: ANS-05 Context completeness
The system SHALL preserve required conditions and exception context within a checked generation budget.

#### Scenario: Evidence exceeds budget
- **GIVEN** an answer requiring more mandatory context than the configured limit
- **WHEN** context is assembled
- **THEN** the system requests clarification or reports insufficient evidence rather than claiming completeness.
