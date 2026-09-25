"""Generation-based ingestion into Memgraph.

Each ingest builds a complete new index generation next to the published one:
every node carries its generation_id, and a :Publication pointer per snapshot
names the generation queries use. The pointer moves only after the new
generation is written and verified, in one transaction. A failure leaves the
pointer, and the generation it names, untouched.

One previous generation is kept for rollback. Anything older is retired and
deleted. A document missing from a new manifest is therefore retired with
the generation that contained it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from neo4j import GraphDatabase

from app.chunking.chunk import ChildChunk, ChunkConfig, chunk_document
from app.chunking.parse import Section, parse_sections
from app.doctor import load_lock
from app.embeddings import FORMAT_VERSION, cosine
from app.sources import Finding, Snapshot, SourceDocument, load_snapshot, publication_decision, validate_snapshot
from app.state import State, now

READBACK_TOLERANCE = 1e-6
SELF_MATCH_MIN = 0.999
BATCH = 64


class IngestError(RuntimeError):
    pass


class PublicationRefused(IngestError):
    def __init__(self, reason: str, findings: list[Finding]):
        super().__init__(reason)
        self.findings = findings


@dataclass(frozen=True)
class DocumentPlan:
    source: SourceDocument
    sections: list[Section]
    chunks: list[ChildChunk]


@dataclass(frozen=True)
class Plan:
    snapshot: Snapshot
    documents: list[DocumentPlan]
    fingerprint: dict
    generation_id: str

    @property
    def chunks(self) -> list[ChildChunk]:
        return [chunk for doc in self.documents for chunk in doc.chunks]


def input_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_plan(snapshot: Snapshot, embedder, *, profile: str = "ordinary", config: ChunkConfig | None = None) -> Plan:
    """Parse, chunk, and check every input fits, before anything is embedded or written."""
    settings = config or ChunkConfig()
    tokenizer = embedder.tokenizer
    documents = []
    for source in snapshot.documents:
        sections = parse_sections(source.text, document_version_id=source.document_version_id, document_title=source.document_title)
        ids = [section.section_id for section in sections]
        if len(ids) != len(set(ids)):
            raise IngestError(f"{source.document_version_id} has repeated section headings; section ids would collide")
        chunks = chunk_document(
            source.text,
            document_version_id=source.document_version_id,
            document_title=source.document_title,
            tokenizer=tokenizer,
            config=settings,
        )
        check_coverage(source, sections, chunks)
        documents.append(DocumentPlan(source, sections, chunks))
    all_chunks = [chunk for doc in documents for chunk in doc.chunks]
    embedder.check_lengths([chunk.embedding_input for chunk in all_chunks])
    fingerprint = {
        "snapshot_id": snapshot.snapshot_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "documents": sorted((d.document_version_id, d.actual_sha256) for d in snapshot.documents),
        "chunker": settings.fingerprint(tokenizer.name),
        "embedder": embedder.identity,
        "format_version": FORMAT_VERSION,
        "profile": profile,
    }
    raw = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    generation_id = "gen-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return Plan(snapshot, documents, fingerprint, generation_id)


def check_coverage(source: SourceDocument, sections: list[Section], chunks: list[ChildChunk]) -> None:
    """Every non-space character of every section body is inside some chunk span."""
    covered = bytearray(len(source.text))
    for chunk in chunks:
        for start, end in chunk.spans:
            if not (0 <= start < end <= len(source.text)):
                raise IngestError(f"{chunk.chunk_id} span {start}:{end} is outside {source.document_version_id}")
            covered[start:end] = b"\x01" * (end - start)
    for section in sections:
        for offset in range(section.body_start, section.body_end):
            if not covered[offset] and not source.text[offset].isspace():
                raise IngestError(
                    f"{source.document_version_id} {section.heading_path!r} offset {offset} is not covered by any chunk"
                )


def embed_plan(plan: Plan, embedder, state: State, log: Callable[[str], None]) -> dict[str, list[float]]:
    chunks = plan.chunks
    keys = {chunk.chunk_id: input_sha256(chunk.embedding_input) for chunk in chunks}
    cached = state.cached_vectors(list(set(keys.values())), embedder.identity)
    missing = [chunk for chunk in chunks if keys[chunk.chunk_id] not in cached]
    log(f"embedding {len(chunks)} chunks: {len(chunks) - len(missing)} cached, {len(missing)} to encode")
    if missing:
        vectors = embedder.embed([chunk.embedding_input for chunk in missing])
        fresh = {keys[chunk.chunk_id]: vector for chunk, vector in zip(missing, vectors)}
        state.store_vectors(fresh, embedder.identity)
        cached.update(fresh)
    return {chunk.chunk_id: cached[keys[chunk.chunk_id]] for chunk in chunks}


class GraphStore:
    def __init__(self, session, index: str):
        self.session = session
        self.index = index

    def run(self, query: str, **params):
        return self.session.run(query, **params)

    def pointer(self, snapshot_id: str) -> dict | None:
        row = self.run(
            "MATCH (p:Publication {snapshot_id: $s}) RETURN p.current AS current, p.previous AS previous, p.updated_at AS updated_at",
            s=snapshot_id,
        ).single()
        return dict(row) if row else None

    def generation(self, generation_id: str) -> dict | None:
        row = self.run("MATCH (g:IndexGeneration {id: $g}) RETURN properties(g) AS g", g=generation_id).single()
        return dict(row["g"]) if row else None

    def index_size(self) -> int:
        rows = self.run("CALL vector_search.show_index_info() YIELD * RETURN *").data()
        match = next((row for row in rows if row["index_name"] == self.index), None)
        if match is None:
            raise IngestError(f"vector index {self.index} is missing")
        return int(match["size"])

    def delete_generation(self, generation_id: str, *, keep_record: bool = False) -> int:
        removed = self.run(
            "MATCH (n) WHERE n.generation_id = $g AND NOT n:IndexGeneration DETACH DELETE n RETURN count(n) AS n",
            g=generation_id,
        ).single()["n"]
        if not keep_record:
            self.run("MATCH (g:IndexGeneration {id: $g}) DETACH DELETE g", g=generation_id).consume()
        return int(removed)

    def free_memory(self) -> None:
        # A vector index keeps deleted nodes until garbage collection runs.
        self.run("FREE MEMORY").consume()

    def write_generation(self, plan: Plan, vectors: dict[str, list[float]], meta: dict) -> None:
        gen = plan.generation_id
        self.run(
            "CREATE (g:IndexGeneration $props)",
            props={**meta, "id": gen, "status": "building", "created_at": now()},
        ).consume()
        for doc in plan.documents:
            self._write_document(gen, doc, vectors, meta)
        for doc in plan.documents:
            if doc.source.supersedes:
                self.run(
                    "MATCH (new:PolicyVersion {id: $new}), (old:PolicyVersion {id: $old}) "
                    "CREATE (new)-[:SUPERSEDES {generation_id: $g, validation_status: 'manifest-metadata'}]->(old)",
                    new=f"{gen}:{doc.source.document_version_id}",
                    old=f"{gen}:{doc.source.supersedes}",
                    g=gen,
                ).consume()

    def _write_document(self, gen: str, doc: DocumentPlan, vectors: dict[str, list[float]], meta: dict) -> None:
        src = doc.source
        version_id = f"{gen}:{src.document_version_id}"
        self.run(
            "MATCH (g:IndexGeneration {id: $g}) "
            "MERGE (p:Policy {id: $policy_node}) "
            "ON CREATE SET p.generation_id = $g, p.corpus_id = $corpus, p.policy_id = $policy_id, p.issuer = $issuer "
            "CREATE (v:PolicyVersion $props) "
            "CREATE (p)-[:HAS_VERSION {generation_id: $g}]->(v) "
            "CREATE (g)-[:CONTAINS {generation_id: $g}]->(v)",
            g=gen,
            policy_node=f"{gen}:{src.corpus_id}:{src.policy_id}",
            corpus=src.corpus_id,
            policy_id=src.policy_id,
            issuer=src.policy_issuer,
            props={**src.metadata(), "id": version_id, "generation_id": gen, "document_title": src.document_title},
        ).consume()
        self.run(
            "MATCH (v:PolicyVersion {id: $v}) UNWIND $sections AS s "
            "CREATE (v)-[:HAS_SECTION {generation_id: $g}]->(:Section {id: s.id, generation_id: $g, section_id: s.section_id, "
            "document_version_id: $dvid, heading: s.heading, heading_path: s.heading_path, source_start: s.start, source_end: s.end})",
            v=version_id,
            g=gen,
            dvid=src.document_version_id,
            sections=[
                {
                    "id": f"{gen}:{section.section_id}",
                    "section_id": section.section_id,
                    "heading": section.heading,
                    "heading_path": section.heading_path,
                    "start": section.body_start,
                    "end": section.body_end,
                }
                for section in doc.sections
            ],
        ).consume()
        rows = [self._chunk_row(gen, src, chunk, vectors[chunk.chunk_id], meta) for chunk in doc.chunks]
        for start in range(0, len(rows), BATCH):
            self.run(
                "UNWIND $rows AS r MATCH (s:Section {id: r.section_node}) "
                "CREATE (s)-[:HAS_CHUNK {generation_id: $g}]->(c:Chunk) SET c = r.props",
                rows=rows[start : start + BATCH],
                g=gen,
            ).consume()

    @staticmethod
    def _chunk_row(gen: str, src: SourceDocument, chunk: ChildChunk, vector: list[float], meta: dict) -> dict:
        return {
            "section_node": f"{gen}:{chunk.parent_id}",
            "props": {
                "id": f"{gen}:{chunk.chunk_id}",
                "chunk_id": chunk.chunk_id,
                "generation_id": gen,
                "corpus_id": src.corpus_id,
                "policy_id": src.policy_id,
                "version": src.version,
                "document_version_id": src.document_version_id,
                "document_title": src.document_title,
                "publication_status": src.publication_status,
                "effective_from": src.effective_from,
                "effective_to": src.effective_to,
                "section_id": chunk.parent_id,
                "heading_path": chunk.heading_path,
                "text": chunk.text,
                "source_spans": json.dumps(chunk.spans),
                "source_start": chunk.source_start,
                "source_end": chunk.source_end,
                "token_count": chunk.token_count,
                "part_index": chunk.part_index,
                "continuation_of": chunk.continuation_of,
                "exception_refs": list(chunk.exception_refs),
                "table_header": chunk.table_header,
                "embedding_input_hash": input_sha256(chunk.embedding_input),
                "chunker_config_hash": chunk.chunker_config_hash,
                "embedding_model": meta["embedding_model"],
                "embedding_revision": meta["embedding_revision"],
                "tokenizer_revision": meta["tokenizer"],
                "embedding_dimension": meta["dimensions"],
                "embedding": vector,
            },
        }

    def verify(self, plan: Plan, vectors: dict[str, list[float]], index_before: int) -> dict:
        gen = plan.generation_id
        counts = self.run(
            "MATCH (n) WHERE n.generation_id = $g RETURN labels(n)[0] AS label, count(n) AS n", g=gen
        ).data()
        counts = {row["label"]: row["n"] for row in counts}
        expected = {
            "PolicyVersion": len(plan.documents),
            "Section": sum(len(doc.sections) for doc in plan.documents),
            "Chunk": len(plan.chunks),
        }
        for label, n in expected.items():
            if counts.get(label, 0) != n:
                raise IngestError(f"{label} count {counts.get(label, 0)} != expected {n}")
        index_after = self.index_size()
        if index_after != index_before + len(plan.chunks):
            raise IngestError(f"vector index size {index_after} != {index_before} + {len(plan.chunks)}")
        drift = 0.0
        stored = {
            row["chunk_id"]: list(row["embedding"])
            for row in self.run(
                "MATCH (c:Chunk {generation_id: $g}) RETURN c.chunk_id AS chunk_id, c.embedding AS embedding", g=gen
            ).data()
        }
        for chunk_id, vector in vectors.items():
            drift = max(drift, max(abs(a - b) for a, b in zip(vector, stored[chunk_id])))
        if drift > READBACK_TOLERANCE:
            raise IngestError(f"stored embeddings drift {drift:.2e} from the encoded vectors")
        worst = 1.0
        for chunk_id, vector in vectors.items():
            hits = self.run(
                "CALL vector_search.search($index, $k, $v) YIELD node, similarity "
                "WHERE node.generation_id = $g RETURN node.chunk_id AS chunk_id, similarity ORDER BY similarity DESC LIMIT 1",
                index=self.index,
                k=index_after,
                v=vector,
                g=gen,
            ).data()
            if not hits or hits[0]["similarity"] < SELF_MATCH_MIN:
                raise IngestError(f"chunk {chunk_id} is not its own nearest neighbour in the vector index")
            if hits[0]["chunk_id"] != chunk_id:
                if abs(cosine(vector, stored[hits[0]["chunk_id"]]) - 1.0) > 1e-6:
                    raise IngestError(f"chunk {chunk_id} is not its own nearest neighbour in the vector index")
            worst = min(worst, float(hits[0]["similarity"]))
        return {
            "node_counts": counts,
            "index_size_before": index_before,
            "index_size_after": index_after,
            "max_readback_drift": drift,
            "min_self_similarity": worst,
        }

    def publish(self, snapshot_id: str, generation_id: str) -> dict:
        """Move the pointer in one transaction. Returns the generation to retire, if any."""

        def swap(tx):
            row = tx.run(
                "MERGE (p:Publication {snapshot_id: $s}) RETURN p.current AS current, p.previous AS previous", s=snapshot_id
            ).single()
            current, previous = row["current"], row["previous"]
            if current == generation_id:
                return {"current": current, "previous": previous, "retire": None}
            tx.run("MATCH (g:IndexGeneration {id: $g}) SET g.status = 'published', g.published_at = $t", g=generation_id, t=now())
            if current:
                tx.run("MATCH (g:IndexGeneration {id: $g}) SET g.status = 'previous'", g=current)
            retire = previous if previous and previous not in (generation_id, current) else None
            if retire:
                tx.run("MATCH (g:IndexGeneration {id: $g}) SET g.status = 'retired'", g=retire)
            tx.run(
                "MATCH (p:Publication {snapshot_id: $s}) SET p.current = $new, p.previous = $old, p.updated_at = $t",
                s=snapshot_id,
                new=generation_id,
                old=current,
                t=now(),
            )
            return {"current": generation_id, "previous": current, "retire": retire}

        return self.session.execute_write(swap)


def generation_meta(plan: Plan, embedder, *, profile: str, reason: str | None, findings: list[Finding]) -> dict:
    identity = embedder.identity
    snap = plan.snapshot
    return {
        "generation_id": plan.generation_id,
        "snapshot_id": snap.snapshot_id,
        "corpus_id": snap.corpus_id,
        "as_of": snap.as_of,
        "manifest_sha256": snap.manifest_sha256,
        "profile": profile,
        "profile_reason": reason,
        "findings": json.dumps([f.as_dict() for f in findings]),
        "chunker_config_hash": plan.fingerprint["chunker"],
        "format_version": FORMAT_VERSION,
        "embedder": json.dumps(identity, sort_keys=True),
        "embedding_model": identity["model"],
        "embedding_revision": identity["revision"],
        "tokenizer": identity.get("tokenizer"),
        "dimensions": identity["dimensions"],
        "document_count": len(plan.documents),
        "chunk_count": len(plan.chunks),
    }


def connect(bolt: str | None = None):
    lock = load_lock()
    return GraphDatabase.driver(bolt or lock["memgraph"]["bolt_url"], auth=None), lock["memgraph"]["vector_index"]


def ingest(
    snapshot_id: str,
    *,
    profile: str = "ordinary",
    reason: str | None = None,
    embedder=None,
    bolt: str | None = None,
    state: State | None = None,
    log: Callable[[str], None] = print,
    config: ChunkConfig | None = None,
    fail_after_write: bool = False,
) -> dict:
    if profile not in ("ordinary", "evaluation"):
        raise ValueError(f"unknown profile {profile!r}")
    state = state or State()
    run_id = f"ingest-{uuid.uuid4().hex[:12]}"
    state.start_run(run_id, "ingest", snapshot_id)
    report: dict = {"run_id": run_id, "snapshot_id": snapshot_id, "profile": profile, "reason": reason}
    try:
        snapshot = load_snapshot(snapshot_id)
        findings = validate_snapshot(snapshot)
        report["findings"] = [f.as_dict() for f in findings]
        allowed, decision = publication_decision(findings, profile=profile, reason=reason)
        report["decision"] = decision
        for finding in findings:
            log(f"{finding.severity:7} {finding.code}: {finding.document_version_id or snapshot_id}: {finding.message}")
        log(decision)
        if not allowed:
            raise PublicationRefused(decision, findings)

        if embedder is None:
            from app.embedder import embedder_from_lock

            embedder = embedder_from_lock(load_lock())
        plan = build_plan(snapshot, embedder, profile=profile, config=config)
        gen = plan.generation_id
        report["generation_id"] = gen
        report["fingerprint"] = plan.fingerprint
        report["documents"] = [
            {
                "document_version_id": doc.source.document_version_id,
                "sections": len(doc.sections),
                "chunks": len(doc.chunks),
                "max_chunk_tokens": max((c.token_count for c in doc.chunks), default=0),
            }
            for doc in plan.documents
        ]
        log(f"plan {gen}: {len(plan.documents)} documents, {sum(len(d.sections) for d in plan.documents)} sections, {len(plan.chunks)} chunks")

        driver, index = connect(bolt)
        try:
            with driver.session() as session:
                store = GraphStore(session, index)
                pointer = store.pointer(snapshot_id)
                existing = store.generation(gen)
                if pointer and pointer["current"] == gen and existing and existing["status"] == "published":
                    report.update(status="unchanged", publication=pointer)
                    log(f"{gen} is already the published generation for {snapshot_id}; nothing to do")
                    state.finish_run(run_id, "unchanged", report, gen)
                    return report
                if existing:
                    log(f"removing earlier {existing['status']} copy of {gen} before rebuilding")
                    store.delete_generation(gen)
                    store.free_memory()

                vectors = embed_plan(plan, embedder, state, log)
                index_before = store.index_size()
                meta = generation_meta(plan, embedder, profile=profile, reason=reason, findings=findings)
                try:
                    store.write_generation(plan, vectors, meta)
                    if fail_after_write:
                        raise IngestError("injected failure after writing, before publication")
                    report["verification"] = store.verify(plan, vectors, index_before)
                    store.run(
                        "MATCH (g:IndexGeneration {id: $g}) SET g.status = 'complete', g.completed_at = $t",
                        g=gen,
                        t=now(),
                    ).consume()
                except Exception:
                    store.delete_generation(gen, keep_record=True)
                    store.run("MATCH (g:IndexGeneration {id: $g}) SET g.status = 'failed', g.failed_at = $t", g=gen, t=now()).consume()
                    store.free_memory()
                    raise
                log(
                    f"verified {gen}: index {report['verification']['index_size_before']} -> "
                    f"{report['verification']['index_size_after']}, readback drift {report['verification']['max_readback_drift']:.1e}, "
                    f"min self-similarity {report['verification']['min_self_similarity']:.6f}"
                )
                moved = store.publish(snapshot_id, gen)
                if moved["retire"]:
                    removed = store.delete_generation(moved["retire"], keep_record=True)
                    store.free_memory()
                    log(f"retired {moved['retire']} ({removed} nodes removed)")
                report["publication"] = {k: moved[k] for k in ("current", "previous")}
                report["retired"] = moved["retire"]
                log(f"published {gen} for {snapshot_id} (previous: {moved['previous']})")
        finally:
            driver.close()
        report["status"] = "published"
        state.finish_run(run_id, "published", report, gen)
        return report
    except PublicationRefused:
        report["status"] = "refused"
        state.finish_run(run_id, "refused", report)
        raise
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{exc.__class__.__name__}: {exc}"
        state.finish_run(run_id, "failed", report, report.get("generation_id"))
        raise


def rollback(snapshot_id: str, *, bolt: str | None = None, state: State | None = None, log: Callable[[str], None] = print) -> dict:
    state = state or State()
    run_id = f"rollback-{uuid.uuid4().hex[:12]}"
    state.start_run(run_id, "rollback", snapshot_id)
    driver, index = connect(bolt)
    try:
        with driver.session() as session:
            store = GraphStore(session, index)
            pointer = store.pointer(snapshot_id)
            if not pointer or not pointer["previous"]:
                raise IngestError(f"{snapshot_id} has no previous generation to roll back to")
            target = store.generation(pointer["previous"])
            if not target or target["status"] != "previous":
                raise IngestError(f"previous generation {pointer['previous']} is not available")
            moved = store.publish(snapshot_id, pointer["previous"])
    finally:
        driver.close()
    report = {"run_id": run_id, "snapshot_id": snapshot_id, "status": "rolled_back", "from": pointer["current"], "to": moved["current"]}
    log(f"{snapshot_id}: rolled back from {pointer['current']} to {moved['current']}")
    state.finish_run(run_id, "rolled_back", report, moved["current"])
    return report


def index_status(*, bolt: str | None = None) -> dict:
    driver, index = connect(bolt)
    try:
        with driver.session() as session:
            store = GraphStore(session, index)
            pointers = session.run(
                "MATCH (p:Publication) RETURN p.snapshot_id AS snapshot_id, p.current AS current, p.previous AS previous, "
                "p.updated_at AS updated_at ORDER BY snapshot_id"
            ).data()
            generations = session.run(
                "MATCH (g:IndexGeneration) OPTIONAL MATCH (c:Chunk {generation_id: g.id}) "
                "RETURN g.id AS id, g.snapshot_id AS snapshot_id, g.status AS status, g.profile AS profile, "
                "g.chunk_count AS chunk_count, count(c) AS stored_chunks, g.embedding_model AS model, g.created_at AS created_at "
                "ORDER BY created_at"
            ).data()
            return {"vector_index": index, "index_size": store.index_size(), "publications": pointers, "generations": generations}
    finally:
        driver.close()
