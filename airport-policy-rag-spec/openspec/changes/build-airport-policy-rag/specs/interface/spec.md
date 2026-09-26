# interface capability

## ADDED Requirements

### Requirement: UI-01 Evidence inspection
The system SHALL let users inspect citations and concise retrieval traces.

#### Scenario: Open citation
- **GIVEN** an answer contains a citation
- **WHEN** the user opens it
- **THEN** the original excerpt, document version, and section are displayed.

### Requirement: UI-02 Scoped corpus selection
The system SHALL expose the available corpus contexts and distinguish policy issuers.

#### Scenario: Multiple aviation examples
- **GIVEN** several imported corpora are available
- **WHEN** the user asks an issuer-ambiguous question
- **THEN** the interface or triage requests a context instead of blending airline rules.

### Requirement: UI-03 Accessible and honest status
The interface SHALL communicate unavailable, conflicting, insufficient, and successful outcomes without fabricated metrics.

#### Scenario: Model unavailable
- **GIVEN** the local generation service is down
- **WHEN** a user submits a question
- **THEN** the UI displays a useful unavailable state rather than a fabricated answer.
