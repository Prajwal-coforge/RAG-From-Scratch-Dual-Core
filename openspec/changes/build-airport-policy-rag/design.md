# Technical Design

# Airport Policy RAG — Development Specification

Version: 1.2 · Prepared 2026-09-24 · Revised 2026-09-25: data governance layer and authentication removed; embeddings through sentence-transformers, BM25 keyword retrieval, non-gating LLM-judge report, needle retrieval check
Status: approved project direction; implementation and performance remain unverified.
Audience: the development agent on the user's work laptop.

## 1. Objective and decisions

Build a working local internal policy assistant for airport/airline staff. It must retrieve policy evidence, follow relevant policy relationships, and answer with document/section citations. Deliver a reproducible lab submission covering the supplied 100-point RAG rubric.

Use the DecisionsDev/policy-corpus aviation examples as the imported corpus. “Airport corpus” in this specification means the three aviation-related documents identified below; it does not mean a single real airport's policy collection.

Decisions:
- Local sentence-transformers for document/query embeddings (EmbeddingGemma) and reranking, as the assignment names. Local Ollama for corpus generation, agent reasoning, and answer generation.
- Memgraph for vector persistence/search and policy relationships; no Chroma.
- A local cross-encoder for reranking through sentence-transformers.
- A JavaScript frontend using React and Vite.
- A Python backend using FastAPI and Pydantic.
- No data governance layer: no authentication, user identities, roles, per-document or per-section access control, or audit log. The application serves one local user, and every indexed policy is readable.
- OpenSpec for development requirements and change tracking.
- No data lake, object-storage service, lakehouse, warehouse, or Spark. Ingest stays snapshot → validate → chunk → embed → index. `policy-rag etl` also writes bronze, silver, and gold JSON under `.local/medallion/`; retrieval does not read those files (`docs/decisions/0006-medallion-zones-without-a-lake.md`).
- Ordinary version-controlled source fixtures, local build artifacts, SQLite application metadata, and the Memgraph volume are sufficient storage.
- No hosted model fallback, cloud tracing, public deployment, or external account requirement.

The user selected Memgraph and Ollama as alternatives to the assignment's suggested stack. The original Part 2 also names Chroma and sentence-transformers explicitly. Record these substitutions in the submission; do not claim instructor approval or guarantee a grade. Continue with the user's chosen stack.

## 2. Success and scope

A staff member selects a corpus context, asks a question, and receives a grounded answer or an explicit clarification, conflict, or insufficient-evidence response. They can inspect source excerpts and a concise retrieval trace.

Required:
1. Real embed/store/retrieve smoke test on two texts before full ingestion.
2. Imported aviation corpus and four genuinely LLM-generated lab documents.
3. Versioned, reproducible ingestion and source lineage.
4. Section-aware parent–child chunking and local embeddings.
5. Vector-only, hybrid, hybrid-reranked, graph-reranked, and bounded agentic modes.
6. A working basic RAG CLI and frontend.
7. Automated recall/answer evaluation, source-defect diagnosis, and CI.
8. An ordered screenshot evidence pack and a single submission PDF produced during implementation.

Out of scope:
- Real employee records, production payroll, live flight systems, booking changes, legal/compliance advice, or automated operational decisions.
- Training/fine-tuning embedding models or LLMs.
- A general-purpose autonomous agent with shell, internet, database-write, or unrestricted filesystem access.
- A data governance layer: authentication, sessions, user identities, roles, organization charts, per-document or per-section access control, and audit logging.
- Large-scale infrastructure justified only by hypothetical growth.

All real-world-looking rules in the demonstration are corpus statements or synthetic company rules. Display that distinction; do not present the synthetic emissions policy as actual aviation law.

## 3. Source corpus and provenance

Import exactly these files from https://github.com/DecisionsDev/policy-corpus at commit:
948dacadbe03ca4d978ea3d6ccc19131e6a92efb

| corpus_id | File | SHA-256 | Meaning |
|---|---|---|---|
| skywings-baggage | [luggage/luggage_policy.txt](https://github.com/DecisionsDev/policy-corpus/blob/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/luggage/luggage_policy.txt) | 319cbb92315b52cf683157fef3396efd3fdee8078c6e35deae156656910a8cd2 | SkyWings passenger baggage rules |
| aethersky-compensation | [human-resources/compensation/aethersky-airways-pilot-compensation-policy.txt](https://github.com/DecisionsDev/policy-corpus/blob/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/human-resources/compensation/aethersky-airways-pilot-compensation-policy.txt) | b418ecf530c7fd48fd2c1814adfc25eee84200bfab110ee4bec71c124e4d2f24 | AetherSky pilot employment rules |
| synthetic-emissions | [air_transport/airplane_pollution_compliance.txt](https://github.com/DecisionsDev/policy-corpus/blob/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/air_transport/airplane_pollution_compliance.txt) | 186f4afe7c638dc64fadf9b1ec269a6e90d16a11854fa614d197b14afecabc6f | Fictional environmental-authority scenario |

Verify hashes before ingestion. Never execute downloaded repository code automatically. Retain the upstream Apache-2.0 license and provenance notices with copied material.

Keep policy issuer, source repository, commit, and corpus_id distinct. The three examples are separate contexts; never infer that SkyWings rules apply to AetherSky employees. Selecting several corpora is not permission to blend their rules.

Do not index README files, supplied decision CSVs, test answers, reference Python implementations, generated summaries, or benchmark outputs as policy evidence. Optional luggage decision datasets may be used only as evaluation inputs after reviewing reference assumptions. They do not contain our required retrieval relevance labels.

### Corpus navigation and ingestion scope

Use these folder links for browsing; ingestion is restricted to the three individual policy files linked above and pinned in `config/corpus-manifest.json`.

| Folder | Purpose | Ingestion rule |
|---|---|---|
| [luggage/](https://github.com/DecisionsDev/policy-corpus/tree/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/luggage) | Primary baggage-policy use case | Import only `luggage_policy.txt` |
| [human-resources/compensation/](https://github.com/DecisionsDev/policy-corpus/tree/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/human-resources/compensation) | Pilot compensation use case | Import only `aethersky-airways-pilot-compensation-policy.txt` |
| [air_transport/](https://github.com/DecisionsDev/policy-corpus/tree/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/air_transport) | Synthetic aviation emissions use case | Import only `airplane_pollution_compliance.txt` |
| [luggage/luggage_compliance/](https://github.com/DecisionsDev/policy-corpus/tree/948dacadbe03ca4d978ea3d6ccc19131e6a92efb/luggage/luggage_compliance) | Optional reference logic and decision datasets for evaluation | Never index code, CSV labels, or expected answers as policy evidence |

Start implementation with baggage, then add the other two issuer contexts. Do not recursively ingest the repository. `luggage/luggage_policy.md` is supporting documentation and is excluded from the policy index. These aviation examples supplement the four generated airport-policy documents required below.

All links in this section point to the pinned revision. The manifest supplies raw download URLs and SHA-256 hashes; verify them before ingestion. A future upstream refresh requires an explicit manifest update and evaluation rerun.

Known source gaps:
- SkyWings baggage text references a Dangerous Goods Policy not included in the curated files.
- AetherSky describes base pay by rank/aircraft but supplies no base-rate table.
These are useful abstention tests, not evidence that the developer deliberately planted the assignment's defect.

## 4. Generated documents required by the rubric

Create a fictional airport operator named AeroPolicy Airport. Generate the following four prose documents through the local LLM, each 500–800 words excluding front matter. Save the prompts, model digest, timestamp, generated raw text, and final reviewed text. Do not fabricate generation logs.

1. AP-BAG-001 v2: Staff Baggage Handling and Escalation.
2. AP-INC-002 v1: Operational Incident Response and Review.
3. AP-SEC-003 v1: Staff Access, Restricted Items, and Approvals.
4. AP-BAG-001 v1: an obsolete duplicate with a conflicting escalation deadline.

Create numbered sections and explicit cross-document references. Define v2's internal baggage-incident escalation deadline as 10 minutes and obsolete v1's as 30 minutes. These are invented internal demonstration rules. Include the same question-relevant conditions in both clauses, so the difference is genuinely the deadline rather than applicability.

The current baggage policy must refer to the incident procedure and the restricted-items approval procedure. AP-SEC-003 names the staff roles and approval steps for restricted items as policy content; those roles do not control who can read the documents.

Assign explicit, reviewed version/effective-date metadata. A suggested fixed sequence is:
- v1 effective 2025-01-01 through 2025-06-30;
- v2 effective from 2025-07-01;
- lab questions use as_of 2025-08-01.
These dates are fixture choices, not imported source facts.

Maintain separate immutable manifests:
- clean: three current policies;
- duplicate: three current policies plus the obsolete duplicate;
- dirty-stale: a deliberately stale source delivery containing obsolete AP-BAG-001 and the other two policies, with AP-BAG-001 incorrectly supplied as the active version;
- historical: old versions, used only when a question explicitly asks about history.

The dirty-stale fixture represents a source catalog problem. Preserve the original version metadata separately and record the precise corruption in the fixture manifest. Do not alter production code or secretly bypass validation to create an error.

The diagnosis must show the actual question, retrieved faulty clause, unedited model response, expected current rule, source-delivery defect, and clean rerun. Retrieve the correct clause within the stale input and establish that the new clause was absent from that supplied input. If retrieval misses an available correct clause or the model invents information, record that as an additional retrieval/generation failure instead of falsely attributing everything to data quality. If no flawed answer is observed, do not fabricate one; continue with a documented source-defect case and report the remaining rubric-evidence gap.

Imported examples supplement these generated documents. They do not replace the assignment's source-generation requirement.

## 5. Architecture

~~~mermaid
flowchart TD
    S[Versioned policy files and manifests] --> I[Parse and validate]
    I --> C[Section-aware child chunks and parents]
    C --> E[sentence-transformers EmbeddingGemma]
    E --> M[Memgraph vectors and policy graph]
    I --> G[Validated policy relationships]
    G --> M
    U[React JavaScript UI or CLI] --> A[FastAPI backend]
    A --> T[Policy triage]
    T --> O[Deterministic pipeline or bounded Deep Agents]
    O --> R[Retrieval gateway]
    R <--> M
    R --> K[Cross-encoder reranking]
    K --> P[Parent and exception context]
    P --> L[Ollama answer generation]
    L --> V[Citation and evidence checks]
    V --> U
~~~

The backend is the only client of Memgraph and model services. The browser receives no database credentials or unrestricted graph endpoint. SQLite stores dataset/index manifests and run records. It is not a second vector store.

Use a modular backend.

## 6. Runtime and configuration

Proposed defaults:
- Python 3.11+ compatible with locked dependencies.
- React + Vite, JavaScript (JSX); package lock committed.
- Memgraph Community with a persistent local volume, a pinned compatible image, and required vector procedures verified.
- google/embeddinggemma-300m through sentence-transformers, pinned revision, full 768-dimensional vectors. The Hugging Face repository is gated: accept the Gemma license and authenticate locally once; never commit the token. Ollama embeddinggemma served the milestone 1 proof and stays available only as a recorded earlier configuration, never mixed into the same index.
- Ollama qwen3:8b for chat/tool calling. Preflight memory and actual tool-call compatibility before enabling agent mode.
- cross-encoder/ms-marco-MiniLM-L6-v2 through sentence-transformers; pin resolved model revision.
- pytest for automated tests; Playwright for frontend behavior and screenshots.
- ReportLab or another local PDF generator for the final evidence PDF.

Do not invent dependency versions. Resolve compatible versions during preflight, create lockfiles, and record exact model digests, tokenizer revisions, Memgraph image digest, OS, memory, and accelerator availability. Smaller local chat-model alternatives may be evaluated if hardware requires them; record the decision and rerun the same tests. Never silently switch to a hosted service.

Backend on host + Memgraph in Docker + Ollama on host is the initial deployment. Make host/container URLs configurable; localhost has different meanings inside a container. Bind development services to loopback where practical.

Check actual sentence-transformers embeddings and /api/chat responses, 768-vector length, tokenizer loading, cross-encoder inference, Memgraph persistence after restart, and one tool call through the selected local agent adapter.

## 7. Data contracts

Identifiers must be stable, deterministic, and collision-resistant:
- policy_id: logical policy identity within a corpus;
- document_version_id: corpus + policy_id + source version/content hash;
- section_id: version + normalized section path/offset;
- clause_id: stable evaluation annotation within a document version;
- chunk_id: version + source span + chunker configuration hash;
- index_generation_id: complete ingestion/model/configuration fingerprint.

Document metadata:
corpus_id, policy_issuer, policy_id, version, title, source_type
(imported/generated), source_uri, source_commit, content_sha256, license,
effective_from/to (nullable if unknown), publication_status, owner,
fixture_state.

Unknown effective dates remain unknown. Never convert Git commit dates into policy effective dates. Ordinary queries use the dataset manifest's selected approved version when authoritative dates are unavailable, with that limitation visible.

Section/chunk metadata:
document_version_id, section_id, heading_path, parent_id, source_start/end,
clause_ids, original_text, normalized_text, embedding_input_hash,
embedding_model_digest, tokenizer_revision, embedding_dimension,
chunker_config_hash, index_generation_id.

Use canonical source text plus a reversible normalization/offset map. Citations must resolve to the original text even if whitespace is normalized. Graph facts must carry supporting source spans.

## 8. Ingestion without a data lake

Pipeline:
1. Load an allowlisted corpus manifest; verify file hashes and provenance.
2. Parse Markdown headings or numbered plain-text sections.
3. Preserve source text; normalize whitespace without deleting conditions.
4. Validate required metadata, references, versions, and duplicate hashes.
5. Build parent sections and child chunks.
6. Extract explicit references deterministically; optionally propose semantic
   relationships with the local LLM, retaining them as unapproved until checked.
7. Embed children and load a new Memgraph index generation.
8. Run structural checks, then atomically publish the generation pointer.

Sources live in data/sources; reproducible temporary outputs in .local/build;
SQLite and Memgraph hold runtime state. Ignore model weights and runtime
stores in Git.

Exact duplicate hashes may share computation, but cannot merge away distinct
provenance. Conflicting versions retain separate identities.
Unresolved references become quality findings, never invented sections.

Support idempotent re-ingestion, changed-document upserts, removed-document
retirement, and rollback to the previous published generation. During a
partial failure, continue serving the previous complete generation.

The damaged lab fixtures may bypass specific data-quality rejection only
through an explicit evaluation profile with recorded reason.

## 9. Chunking

Use structure-aware parent–child chunking.
- Parent: one logical section/subsection.
- Child: target 300 tokens, maximum 400 using the pinned embedding tokenizer.
- Long sections: split on paragraph boundaries, then sentences.
- Overlap: target up to 50 tokens using complete trailing sentences only
  within the same parent.
- Preserve short sections; never pad with unrelated content.
- Keep a condition and its exception together when feasible.
- Split large tables into row groups that repeat column headers and scope.
- Keep explicit exception/reference links when a rule cannot fit in one child.
- Include document title and heading path in embedding/reranker input.

If a sentence or table row exceeds the hard limit, create labeled subspans
with source offsets and continuation/parent links. Do not silently truncate
or produce an over-limit embedding request.

Document versions are a hard boundary. Do not split merely
by characters or assume a generic tokenizer matches either model.

Store original spans and configuration fingerprints. Tests must reconstruct
the source coverage, verify overlap bounds, preserve table labels, and show
that exception references survive.

The settings are experimental defaults. Compare fixed-window baseline and
structure-aware variants at approximately 200/300/400 tokens, plus overlap
0 versus 50, on development questions.

## 10. Embedding strategy

Use the same pinned embeddinggemma model and dimensionality for document
indexing and queries. Use retrieval-specific document/query formatting,
applied exactly once after checking adapter behavior:

~~~text
Document: title: <policy and section> | text: <chunk>
Query: task: search result | query: <question>
~~~

Embed with sentence-transformers `encode` on the already formatted strings,
with no built-in prompt, so the prefix is applied once; the model's own
`query`/`document` prompts would add a second prefix and force `title: none`.
sentence-transformers truncates silently at `max_seq_length`, so count every
formatted input with the model's own tokenizer first and refuse any input over
the limit; this replaces Ollama's truncate=false. Batch inputs. Verify
finite values, vector length 768, and expected normalization. Use cosine
similarity; never compare embeddings from different models just because the
dimension matches.

No LLM-generated summary replaces original policy text in the primary index.
Generated aliases may be additional searchable metadata with provenance,
but are not authoritative evidence.

Cache embeddings by exact formatted input hash plus model digest, dimension,
and preprocessing version. A model or input-format change creates a new index generation and re-embeds
all affected data before publication.

Evaluate EmbeddingGemma against one compatible local challenger only after
the baseline works. Rebuild separate indexes and use identical evaluation
questions. Pin each model's required prompt format.

## 11. Memgraph and graph schema

Required nodes:
Policy, PolicyVersion, Section, Chunk, Role, Department, Control.

Required edges:
HAS_VERSION, HAS_SECTION, HAS_CHUNK, REFERENCES, APPLIES_TO_ROLE,
MAPS_TO_CONTROL. Add SUPERSEDES only from verified version metadata.
Add EXCEPTION_TO only with explicit source support and validated endpoints.

Scope identities by corpus. Role, Department, and Control nodes are policy
concepts named in the sources; they do not control who can read anything.

Each semantic edge includes supporting version/section/span and validation
status. Do not let unverified model-extracted edges affect authoritative
answers. Initial graph construction can be entirely deterministic plus
reviewed manifests.

Create an actual Memgraph vector index and demonstrate it in the two-text
smoke test. Verify procedures against the pinned installed version.

Vector retrieval uses the Memgraph vector index. For this small corpus the
backend may also calculate exact cosine similarity over stored vectors as a
check; label exact search honestly and do not claim ANN performance where
it was not used. No second vector database is needed.

Use parameterized queries and an allowlisted set of retrieval operations.
Agents cannot submit arbitrary Cypher. Restrict exposed graph properties;
do not return vector arrays to the model.

## 12. Retrieval, fusion, graph expansion, and reranking

Request context: selected corpus, approved snapshot, as_of, mode, question,
and server-generated trace ID.

Modes:
- vector: vector retrieval only;
- hybrid: vector + keyword retrieval, rank fusion;
- hybrid_rerank: hybrid followed by cross-encoder;
- graph_rerank: hybrid + bounded graph expansion + cross-encoder;
- agentic: bounded agent chooses the same retrieval tools.

Same corpus, generation prompt, and model across comparisons.
Basic/vector mode remains callable independently of agents.

Initial candidate parameters:
vector top 10; keyword top 10; RRF constant 60; one graph hop; at most 10
additional graph candidates; at most 30 unique reranker candidates.
Cap by available eligible documents. Deduplicate by chunk identity, not
just similar wording or titles.

Keyword retrieval preserves identifiers, section numbers, negation, units,
and acronyms. Implement Okapi BM25 locally without a search library
(k1 = 1.5, b = 0.75, over the same child chunks, including title and heading
text), with a tokenizer that keeps identifiers such as AP-BAG-001, section
numbers such as 4.2, and number-unit pairs such as 23 kg as single terms.
Add a documented exact-match boost when a query identifier or quoted phrase
appears verbatim in a chunk. Record the BM25 score, the boost, and the rank
for every keyword candidate.

RRF combines ranked lists, not raw incomparable scores:
score(d) = sum over matching lists of 1 / (60 + rank_in_list(d)).
Tie-break by stable chunk ID. Pin fusion ordering. Graph additions join the
candidate set with their provenance before cross-encoder scoring.

Reranker: cross-encoder/ms-marco-MiniLM-L6-v2 via sentence-transformers.
Input is (original question, title + heading + candidate text).
Validate the actual paired tokenizer input against 512 tokens, including
special tokens. If needed, split the passage into sentence-aware windows
with retained source spans, score windows, and preserve the selected span.
Do not silently cut away trailing exceptions. Reranker scores are uncalibrated
relevance values, not answer probabilities.

Initially select up to 5 evidence children; report top-3 and top-5 evaluation.
Expand selected evidence with necessary parent/exception clauses.
Deduplicate overlaps, preserve distinct conflicting versions in diagnosis
mode, and pack under a configurable 3,500-token evidence budget counted with
the generator tokenizer. Reserve room for system text, question, and output.
Mandatory dependencies that cannot fit trigger clarification/insufficient
evidence rather than pretending the evidence set is complete.

## 13. Triage and Deep Agents

Triage identifies policy domain, corpus/issuer, required facts, and whether
the request needs a direct lookup, cross-policy lookup, or clarification.
It cannot guess missing applicability facts such as the employee's role or location.

Use LangChain Deep Agents with a verified local ChatOllama-compatible model.
A default cloud model is forbidden. Test tool calling on the work laptop.

Allowed tools:
search_policies(query, modes), get_section(section_id),
follow_policy_links(seed_ids, allowed_relation_types),
compare_versions(policy_id), and optional deterministic arithmetic.

The deterministic pipeline implements vector/keyword/reranker behavior
explicitly; delegating everything to an agent does not satisfy these requirements.

Limit agent runs to 6 tool calls, 1 delegation level, at most 2 scoped
subagents, and 120 seconds initially. Subagents get the same or a narrower
tool set and corpus scope. No persistent memory across runs. Keep per-run
state isolated. Disable/remove shell, arbitrary browsing, unrestricted filesystem,
and database-write tools exposed by the chosen framework. Verify the actual
enabled tool inventory. If framework defaults cannot be safely constrained,
keep agent mode disabled and report the specific issue while continuing the
core pipeline; do not relabel a deterministic workflow as Deep Agents.

On timeout or tool failure, return a structured partial/insufficient-evidence
response. Never conceal a failed agent run by silently switching modes.

Trace tool names, inputs, durations, retrieved
source IDs, paths, and outcomes. Show concise action summaries, not private
model reasoning or raw chain-of-thought.

## 14. Generation, citations, and responses

Call local Ollama /api/chat with low-variance generation settings and record
seed/settings where supported; do not promise exact determinism.

Treat policy text as untrusted evidence. Source text cannot change tools or
instructions. The prompt requires supported
answers, explicit missing-information handling, and precise citations.

Response statuses:
answered, needs_clarification, insufficient_evidence, conflicting_sources,
unavailable.

Response contract:
request_id, status, answer, claims[], citations[], follow_up_questions[],
mode_used, corpus_id, index_generation_id, timing_ms, trace_id.

Each claim identifies supporting citation IDs. Each citation contains a
document title, version, section path, source span, chunk_id, and backend
source URL. Never allow invented citation IDs. Verify every referenced ID is
among the supplied evidence.

Citation validity does not prove semantic entailment. Add deterministic
checks for expected numbers/units/negation in lab tests and a documented
manual review sample for claim support. Any model-based verifier is advisory
and cannot independently certify truth.

For numerical scenarios, retrieve the rule first and use a deterministic
calculator if needed. It must expose inputs/rule citations and abstain when
a needed rate, threshold, or interpretation is absent.

Do not stream unvalidated evidence-bearing answer tokens in v1. Progress
events may stream; the final validated answer is returned atomically.

## 15. API and frontend

Proposed endpoints:
- GET /api/corpora: available corpus contexts
- POST /api/ask
- GET /api/sources/{chunk_id}: source excerpt
- GET /api/traces/{trace_id}: retrieval trace
- GET /api/graph?seed=<id>&depth=1: one-hop policy subgraph
- GET /api/health/live; GET /api/health/ready
- Endpoints for ingest status and evaluation reports.

Ask JSON accepts question (max 2,000 characters), corpus_id, as_of, mode,
and conversation_id if implemented. Server validates snapshot and mode.
Unknown fields and raw Cypher are rejected. A question that names no issuer is routed by the local chat model to one or more published contexts; the user is not asked to pick a corpus. Passages from different issuers stay attributed to their own documents. An explicit snapshot on the CLI remains available for evaluation.

Use clear validation, 404 for unknown source IDs, 422 for malformed
requests, 503 for missing services, and a controlled timeout response. Do
not return stack traces.

Frontend screens:
1. Ask: question, optional date, answer, citations, status. No corpus selector.
2. Evidence drawer: original source excerpts and section/version labels.
3. Explain retrieval: method, selected snippets, graph paths, timing.
4. Evaluation view: actual metrics, run configuration, comparisons.

Keep development knobs in an optional evaluation panel. Keep the damaged
dataset out of model routing. Use accessible controls and responsive layout. No mocked metrics or fabricated
“passing” badges in the final application.

## 16. Evaluation design

Create 12 development questions and at least 12 held-out questions, plus a
separate failure suite. Freeze and hash the held-out file before tuning.
At least 8 fixed cases on the generated lab corpus must run through pytest
for the assignment. Report imported and generated corpus metrics separately.

Each case contains:
id, split, corpus_id, snapshot_id, as_of, question,
expected_status, acceptable_evidence_sets (source clause IDs),
required_answer_facts, prohibited_answer_facts, and rationale.

Human-review expected facts against source clauses before freezing. An LLM
may draft cases but may not supply unverified labels. Benchmark files never
enter the retrieval corpus.

Representative imported questions with reviewed source answers:
- SkyWings economy checked-bag weight: 23 kg (section 4).
- SkyWings bag over 32 kg: cargo rather than checked baggage (section 5).
- SkyWings disability mobility aids: free carriage and 48-hour notice
  (section 12), under this synthetic corpus's rules.
- Full dangerous-goods list: missing referenced policy; do not invent a list.
- AetherSky monthly minimum hours: 75 (section 2.1).
- AetherSky domestic/international per diem: 3.25/5.00 per hour (section 3).
- Exact AetherSky base salary: unavailable base-rate table.
- Synthetic emissions reporting: March 31 for the prior year (section 1.3).

Generated cases must cover current vs obsolete deadlines, a three-policy
reference chain, scope clarification, and direct section-code lookup. Add compositional questions that genuinely require
multiple distinct clauses. Do not construct questions that leak their answers.

Metrics:
- Candidate recall@20: relevant source clauses covered by pre-rerank evidence.
- Final recall@3 and recall@5: relevant clauses covered by ranked evidence.
- For multiple acceptable evidence sets, score against the best fully
  specified acceptable set; document the chosen formula.
- Answer fact accuracy: fraction of required facts correctly expressed,
  with exact numeric/unit checks and supported paraphrase matching. These
  deterministic checks, plus prohibited facts and status, decide pass/fail.
- LLM-judge support score (reported, never gating): the local chat model
  rates each answer claim as supported or unsupported by the cited evidence,
  with a fixed rubric prompt at temperature 0. Disclose that the judge is the
  same model that generated the answer, and record judge/deterministic
  disagreements for manual review.
- Needle retrieval check: plant one unique synthetic sentence (for example a
  made-up form code) in an isolated evaluation index among the real chunks,
  ask for it by code and by paraphrase, and record the rank each mode
  (vector, keyword, hybrid, hybrid_rerank) gives it. The needle never enters
  a published index.
- Case pass rate: expected status, all required facts, and no prohibited facts.
- Citation validity and manually sampled claim support.
- Warm/cold stage latency, p50/p95 for sufficiently many runs, actual run count.

For recall, use stable source clause labels across chunking configurations;
overlap must not inflate relevance counts. Questions with no answer in the
corpus have recall marked N/A and are scored by status.

Project release targets (engineering choices, not promises of rubric marks):
candidate recall >= 0.90, final recall@5 >= 0.85, fact accuracy >= 0.85 on
the frozen answerable suite; citation ID/source validity 100%. Report macro averages and
per-case outcomes, plus case pass rate. Small test sets are illustrative.

Compare:
vector; hybrid; hybrid_rerank; graph_rerank; agentic.
Use the same questions/snapshots and generator settings. Capture
at least one reproducible query where hybrid improves over vector-only.
Select that demonstration on development data and disclose it; do not claim
universal superiority. If graph/agents do not improve accuracy, report their
cost and useful cases honestly. Performance thresholds must not be silently
lowered to make CI green.

## 17. Failure acceptance suite

Automate at least:
1. Prompt injection inside a policy cannot invoke unapproved tools.
2. Agent delegation stays within its tool, step, and time budgets and shares no state across runs.
3. Missing external policy and missing numeric rate produce abstention.
4. Wrong embedding dimensions/model generation fail before publication.
5. Oversized embedding/reranking input is detected, not silently truncated.
6. Deleted/superseded content is retired in the new generation.
7. Partial ingestion rollback keeps the old complete generation available.
8. Ollama/Memgraph/reranker unavailability yields a clear unavailable result.
9. Conflicting active sources are surfaced with citations.

Full source-bearing debug traces are explicit lab artifacts with synthetic
data only.

## 18. CI and reproducibility

Provide a documented one-command local verification entry point and:
- fast lane on every change: formatting/lint, unit tests, parser, chunker,
  API contracts, and frontend tests;
- integration lane: real Memgraph, actual embeddings, reranker, generation,
  and fixed pytest evaluation;
- submission lane: complete evaluation, source-defect experiment, evidence
  export, and PDF validation.

Mocks belong only to unit tests. A passing mocked job is not evidence that
the RAG pipeline works. No silently skipped live tests in submission CI.
Mark a run blocked if required model services are unavailable.

Use either an isolated CI runner provisioned with Ollama/models or an
explicitly configured self-hosted runner. A hosted runner cannot reach the
work laptop's localhost. Never expose the laptop's unauthenticated Ollama
endpoint publicly to make CI work. Do not run untrusted fork pull requests
on a work-laptop self-hosted runner.

Pin dependencies and sources; retain run ID, code commit, model digests,
dataset hash, prompts, configuration, environment, logs, and evaluation JSON.
Archive actual build/test results. Private logs must not be included in
published artifacts.

## 19. Rubric and submission evidence

| Rubric requirement | Points | Required evidence |
|---|---:|---|
| Generated source documents and deliberate defect | 8 | Four 500–800-word generated policies, prompts, marked obsolete duplicate |
| Minimal two-text loop before full build | 7 | Timestamped terminal run and source commit |
| Full chunking, embeddings, vector store | 10 | Code and rationale; actual Memgraph data/index |
| Basic RAG end to end | 10 | CLI question, retrieved evidence, API-generated answer |
| Hybrid retrieval improvement | 12 | Code plus vector/hybrid comparison on one disclosed query |
| Reranking | 8 | Cross-encoder code and before/after ranked results |
| 8+ cases, recall and answer evaluation | 15 | Fixed cases, pytest harness, metric definitions and actual output |
| Planted source-defect diagnosis | 15 | Actual flawed run, retrieved clause, source root cause, clean rerun |
| Source attribution | 5 | Answer citing original document and section |
| Passing CI | 10 | Complete pipeline run with live evaluation |
| Total | 100 | All required evidence, independent of optional features |

Produce the single PDF in the assignment's exact order:
1. Generated source documents with the planted issue identified.
2. Terminal output of the minimal two-text loop.
3. Chunking, embedding, and vector-store code.
4. Basic RAG running on a sample question.
5. Hybrid code and improvement example.
6. Reranking code.
7. Evaluation test set and harness code.
8. Evaluation terminal output with recall/accuracy.
9. Defect question, actual flawed response, and written diagnosis.
10. Source attribution output.
11. Passing full pipeline run.

Use multiple screenshots per item when needed for legibility. Capture real
screens and terminal output; never recreate success output. Graph/OpenSpec
evidence may be an appendix after the required sequence. The PDF is evidence
of implementation, not a substitute for the working repository.

## 20. OpenSpec and implementation sequence

Keep this document as the overarching handoff. The included OpenSpec change
contains proposed behavior; do not mark it implemented or archive it on
initialization. Current specs remain empty until verified changes are merged.

Use proposal/spec/design/tasks separation:
- behavior and scenarios in specs;
- stack, models, schema, algorithm defaults in design;
- concrete implementation and evidence tasks in tasks;
- decisions and experiment outcomes in docs/decisions and docs/experiments.

Sequence:
M0: inspect target workspace, preflight hardware/dependencies, initialize
OpenSpec in the actual project without replacing existing instructions.
M1: real two-text embed/store/retrieve test; save proof before full ingestion.
M2: source manifests, genuine generated policies, and quality fixtures.
M3: parsers, chunking, sentence-transformers embeddings (repeat the two-text
proof with this embedder before full ingestion), Memgraph indexing, and
deterministic basic RAG with citations.
M4: BM25 keyword fusion, cross-encoder, fixed test labels, needle retrieval
check, LLM-judge support report, and first live CI.
M5: graph relationships, policy triage, bounded Deep Agents, and agent
safety tests.
M6: frontend, held-out comparisons, diagnosis, final evidence, and PDF.

Do not postpone evaluation until the last milestone. Each milestone adds
tests and evidence. Mark a task complete only after the associated acceptance
check passes. A truthful failed experiment is retained; missing required
functionality stays open.

## 21. Suggested implementation repository

~~~text
airport-policy-rag/
  README.md
  AGENTS.md
  openspec/
  backend/
    app/{api,ingest,chunking,embeddings,retrieval,graph,rerank,agents,generation,evaluation}/
    tests/{unit,integration,failure,evaluation}/
    pyproject.toml
  frontend/
    src/
    tests/
    package.json
  config/
    models.yaml
    retrieval.yaml
    corpus-manifest.json
  data/
    sources/{imported,generated}/
    manifests/
    evaluation/{dev,heldout,failure}/
  docs/
    decisions/
    experiments/
    rubric-traceability.md
  scripts/
  infra/
    compose.yaml
  .github/workflows/
  artifacts/                 # run-specific lab evidence, sanitized
  .local/                    # ignored runtime state and temporary outputs
~~~

Suggested CLI contract to implement:
~~~text
policy-rag doctor
policy-rag smoke-test
policy-rag corpus import
policy-rag corpus generate
policy-rag ingest --snapshot clean
policy-rag ask --corpus airport-generated --mode hybrid_rerank
policy-rag evaluate --suite heldout --modes vector,hybrid,hybrid_rerank,graph_rerank,agentic
policy-rag diagnose --fixture dirty-stale
policy-rag evidence export
~~~

These commands are desired interfaces, not claims that tools already exist.
The implementation agent may adapt names while maintaining documented behavior.

## 22. Decisions the agent may make and completion criteria

Proceed with routine implementation choices without repeated confirmation.
Inspect existing repository instructions and preserve unrelated work.
Choose compatible libraries and platform paths, record decisions, and keep
the project local. Do not install or reconfigure corporate-wide services.

Ask a focused question only when blocked by missing credentials, restrictions
on the work laptop, an unavailable target repository, or an unresolved
decision that changes required behavior. Never invent access to corporate
systems. Continue independent implementation where possible.

Before declaring complete:
- all rubric capabilities work with real services;
- source-generation evidence exists;
- basic RAG works independently of the agent;
- metrics and known failures are reported honestly;
- the full CI run is real and passing;
- PDF screenshots are readable and in order;
- model/runtime versions and reproduction steps are recorded;
- OpenSpec tasks/specs match verified implementation;
- no data lake, data governance layer, or hosted-model dependency was introduced.

## 23. Primary references checked for this handoff

- Corpus and upstream provenance: https://github.com/DecisionsDev/policy-corpus
- OpenSpec behavior/change concepts: https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md
- EmbeddingGemma model card: https://huggingface.co/google/embeddinggemma-300m
- sentence-transformers usage: https://sbert.net/
- Ollama embeddings (milestone 1 proof): https://docs.ollama.com/api/embed
- EmbeddingGemma dimensions/input formatting: https://ai.google.dev/gemma/docs/embeddinggemma/model_card
- Reranker model: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2
- Reranker input configuration: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/blob/main/config.json
- Memgraph vector procedures and edition-specific access behavior: https://memgraph.com/docs/querying/vector-search
- Deep Agents configuration: https://docs.langchain.com/oss/python/deepagents/customization
- ChatOllama integration: https://docs.langchain.com/oss/python/integrations/chat/ollama

Recheck installed-version APIs during preflight. The selected design is a
project proposal, not proof of performance, implementation, or instructor approval.
