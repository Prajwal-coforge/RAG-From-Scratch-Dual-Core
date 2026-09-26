# agents capability

## ADDED Requirements

### Requirement: AGT-01 Local bounded tool orchestration
The system SHALL use a verified local model and a bounded allowlisted tool set for agentic retrieval.

#### Scenario: Tool-call limit
- **GIVEN** an agent repeatedly requesting searches
- **WHEN** the configured budget is exhausted
- **THEN** the run terminates with an explicit status and recorded tool outcomes.

### Requirement: AGT-02 Delegation stays in scope
The system SHALL give subagents the same or a narrower tool set and corpus scope, with isolated per-run state.

#### Scenario: Subagent broadens query
- **GIVEN** a subagent asks for evidence from a corpus outside its parent's scope
- **WHEN** its retrieval tool executes
- **THEN** the expansion is refused and no state from another run is exposed.

### Requirement: AGT-03 Honest capability reporting
The system SHALL identify unavailable agent functionality without silently substituting a different execution mode.

#### Scenario: Unsupported local tool calling
- **GIVEN** the installed local model fails the tool-call compatibility check
- **WHEN** agentic mode is requested
- **THEN** the system reports unavailability while independently implemented basic modes remain usable.
