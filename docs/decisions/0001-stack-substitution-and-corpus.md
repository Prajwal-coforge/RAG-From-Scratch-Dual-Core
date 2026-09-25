# 0001 — Stack substitution and corpus interpretation

Status: accepted for this project. Not instructor approval, and not a grade claim.
Date: 2026-09-24

The assignment in `airport-policy-rag-spec/ORIGINAL_ASSIGNMENT.txt` suggests a local lab stack and a generated company-policy corpus. This overhaul follows the approved handoff in `airport-policy-rag-spec/PROJECT_SPEC.md` instead of extending the previous Chroma pipeline.

## Stack substitution

| Concern | Assignment wording | Selected stack |
| --- | --- | --- |
| Embeddings | `sentence-transformers`, local, no API key | Ollama `embeddinggemma`, 768-dimensional vectors, `/api/embed`, `truncate=false` |
| Vector store | `chromadb`, local, no account | Memgraph Community with a persistent volume and a real vector index |
| Answer model | an LLM API, hosted APIs allowed | Local Ollama `qwen3:8b` only. No hosted fallback |
| Reranker | `sentence-transformers` cross-encoder | Unchanged: `cross-encoder/ms-marco-MiniLM-L6-v2` |
| Storage architecture | not specified as a lake | No data lake, object store, warehouse, Spark, or medallion zones |
| App shape | scripts and pytest | Python FastAPI backend, React + Vite JavaScript frontend, SQLite for manifests and run records. No authentication or access control (`0004-no-data-governance-layer.md`) |

Chroma stays out. Cloud inference stays out. The previous repository pass (`policies/*.pdf`, `qwen3-embedding:0.6b`, ChromaDB) is the prior retrieval exercise. It is not the corpus or the index for this overhaul.

`qwen3:8b` is present locally (architecture qwen3, Q4_K_M, blob `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`). Its Modelfile temperature is 0.6; answer calls must still set the handoff's low-variance settings explicitly. On 2026-09-24, `policy-rag doctor` sent a temperature-0 tool request and `qwen3:8b` called `add`.

## Corpus interpretation

"Airport corpus" means the three aviation files pinned from `DecisionsDev/policy-corpus` at commit `948dacadbe03ca4d978ea3d6ccc19131e6a92efb`, plus four generated AeroPolicy Airport documents required by the rubric.

Imported files, kept as separate issuers:

| corpus_id | Issuer | File |
| --- | --- | --- |
| `skywings-baggage` | SkyWings Airlines | `luggage/luggage_policy.txt` |
| `aethersky-compensation` | AetherSky Airways | `human-resources/compensation/aethersky-airways-pilot-compensation-policy.txt` |
| `synthetic-emissions` | GAEA (fictional) | `air_transport/airplane_pollution_compliance.txt` |

Hashes and raw URLs are in `airport-policy-rag-spec/config/corpus-manifest.json`. SkyWings rules do not apply to AetherSky employees. Selecting more than one corpus is not permission to blend them.

The four generated documents are still required and do not exist yet:

1. AP-BAG-001 v2 — Staff Baggage Handling and Escalation (10-minute deadline)
2. AP-INC-002 v1 — Operational Incident Response and Review
3. AP-SEC-003 v1 — Staff Access, Restricted Items, and Approvals
4. AP-BAG-001 v1 — obsolete duplicate with a 30-minute deadline

Ingestion is those three imported files and the generated airport policies. Do not index the old `policies/` PDFs, upstream READMEs, decision CSVs, reference code, or evaluation labels.

## OpenSpec

The proposed change `build-airport-policy-rag` is copied to `openspec/changes/build-airport-policy-rag/`. Current specs stay empty. The change is not archived and is not marked implemented.
