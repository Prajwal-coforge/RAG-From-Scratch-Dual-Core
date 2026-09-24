# interface capability

## ADDED Requirements

### Requirement: UI-01 Evidence inspection
The system SHALL let authenticated users inspect authorized citations and concise retrieval traces.

#### Scenario: Open citation
- **GIVEN** an answer contains an authorized citation
- **WHEN** the user opens it
- **THEN** the original excerpt, document version, and section are displayed after reauthorization.

### Requirement: UI-02 Scoped corpus selection
The system SHALL expose only entitled corpus contexts and distinguish policy issuers.

#### Scenario: Multiple aviation examples
- **GIVEN** a user can access several imported corpora
- **WHEN** they ask an issuer-ambiguous question
- **THEN** the interface or triage requests a context instead of blending airline rules.

### Requirement: UI-03 Accessible and honest status
The interface SHALL communicate unavailable, conflicting, insufficient, and successful outcomes without fabricated metrics.

#### Scenario: Model unavailable
- **GIVEN** the local generation service is down
- **WHEN** a user submits a question
- **THEN** the UI displays a useful unavailable state rather than a fabricated answer.
