# governance capability

## ADDED Requirements

### Requirement: DGS-01 Server-authoritative identity
The system SHALL derive identity and permissions from authenticated server-side records.

#### Scenario: Client role spoofing
- **GIVEN** an authenticated employee
- **WHEN** the request includes a manager role or alternate user ID
- **THEN** the supplied security fields are rejected and the employee's privileges remain unchanged.

### Requirement: DGS-02 Default-deny policy access
The system SHALL enforce tenant, corpus, activity, document, section, role, and explicit scope restrictions with deny precedence.

#### Scenario: Department boundary
- **GIVEN** a supervisor with rights in one department
- **WHEN** they request a restricted policy scoped to another department
- **THEN** no restricted content or identifying metadata is exposed.

### Requirement: DGS-03 Complete evidence-path enforcement
The system SHALL authorize all evidence paths including graph expansion, parent retrieval, citations, traces, and subagents.

#### Scenario: Parent expansion
- **GIVEN** an authorized child with a parent containing a forbidden sibling section
- **WHEN** the parent context is requested
- **THEN** only independently authorized spans are returned.

### Requirement: DGS-04 Revocation handling
The system SHALL revalidate permission revisions before returning evidence-bearing responses.

#### Scenario: Permission revoked during generation
- **GIVEN** a user whose access changes after retrieval
- **WHEN** the answer is ready to return
- **THEN** newly forbidden evidence is withheld and the response is recomputed or safely denied.

### Requirement: DGS-05 Derived evidence restrictions
The system SHALL require authorization to the provenance underlying derived facts and graph relationships.

#### Scenario: Restricted relation provenance
- **GIVEN** two readable graph nodes joined by a fact supported by restricted evidence
- **WHEN** the relationship is explored
- **THEN** the unsupported-for-this-user relationship is omitted.

### Requirement: DGS-06 No inferred organizational privilege
The system SHALL grant management-scope access only through explicit policy rules.

#### Scenario: Senior unrelated employee
- **GIVEN** a senior employee outside the permitted role and scope
- **WHEN** they request confidential policy material
- **THEN** seniority alone does not grant access.
