# evaluation capability

## ADDED Requirements

### Requirement: EVA-01 Fixed labeled evaluation
The project SHALL include fixed source-grounded cases measuring retrieval recall and answer correctness separately.

#### Scenario: Evaluation run
- **GIVEN** a frozen test set including at least eight generated-corpus questions
- **WHEN** the automated harness runs
- **THEN** per-case results and separate recall/answer metrics are recorded with configuration fingerprints.

#### Scenario: Deterministic grading with a reported judge
- **GIVEN** an answer, its cited evidence, and the case's required and prohibited facts
- **WHEN** the answer is graded
- **THEN** deterministic fact checks decide pass or fail, and a local LLM-judge support score is reported alongside without changing the outcome.

#### Scenario: Needle retrieval check
- **GIVEN** one unique synthetic sentence added to an isolated evaluation index among the real chunks
- **WHEN** it is requested by its code and by paraphrase in each retrieval mode
- **THEN** the rank each mode gives it is recorded, and the needle never enters a published index.

### Requirement: EVA-02 No benchmark contamination
The system SHALL keep expected answers and decision datasets out of the retrieval corpus.

#### Scenario: Evaluation artifact present
- **GIVEN** benchmark CSVs and expected-answer JSON exist in the project
- **WHEN** corpus ingestion runs
- **THEN** only explicitly allowlisted policy files are indexed.

### Requirement: EVA-03 Source-defect diagnosis
The project SHALL retain actual flawed-run evidence and distinguish source, retrieval, and generation failures.

#### Scenario: Stale-source experiment
- **GIVEN** a controlled stale-source fixture and a reviewed current rule
- **WHEN** the diagnostic question is run
- **THEN** the report traces the retrieved source, actual response, source discrepancy, and corrected rerun without fabricated logs.

### Requirement: EVA-04 Live submission CI
The project SHALL run real embedding, vector-store, reranking, and answer-evaluation checks in submission CI.

#### Scenario: Missing model service
- **GIVEN** the submission runner cannot access its model
- **WHEN** the full pipeline is requested
- **THEN** the run is blocked or failed rather than marked passing through skipped live tests.

### Requirement: EVA-05 Rubric evidence package
The project SHALL produce a single readable PDF in the supplied assignment's screenshot order.

#### Scenario: Submission export
- **GIVEN** all required verified run artifacts exist
- **WHEN** the evidence export is produced
- **THEN** the PDF contains the ordered source, code, execution, evaluation, diagnosis, attribution, and CI evidence.
