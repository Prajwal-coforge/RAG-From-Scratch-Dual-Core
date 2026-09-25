"""The four read-only agent tools, bound to one run's corpus and generation.

Every tool reads the published generation the run was started on. None can
change the corpus, write to Memgraph, or reach the filesystem. Sections are
given short run-local references (S1, S2, ...) so the model does not have to
copy long ids; every chunk a tool returns is registered as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import StructuredTool

from app.graph import section_number
from app.retrieve import FINAL_K, MODES, Pool, search_pool

RELATION_TYPES = ("REFERENCES", "APPLIES_TO_ROLE", "MAPS_TO_CONTROL")
EXCERPT_CHARS = 700
SECTION_CHARS = 2400


@dataclass
class RunContext:
    session: object
    index: str
    embedder: object
    reranker: object
    pool: Pool
    snapshot_id: str
    evidence: list[str] = field(default_factory=list)
    section_refs: dict[str, str] = field(default_factory=dict)
    paths: list[dict] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)

    def ref(self, section_id: str) -> str:
        for ref, sid in self.section_refs.items():
            if sid == section_id:
                return ref
        ref = f"S{len(self.section_refs) + 1}"
        self.section_refs[ref] = section_id
        return ref

    def section_id(self, ref_or_id: str) -> str | None:
        ref_or_id = ref_or_id.strip()
        if ref_or_id in self.section_refs:
            return self.section_refs[ref_or_id]
        return ref_or_id if any(c["section_id"] == ref_or_id for c in self.pool.chunks.values()) else None

    def register(self, chunk_id: str) -> None:
        if chunk_id not in self.evidence:
            self.evidence.append(chunk_id)

    def section_chunks(self, section_id: str) -> list[dict]:
        eligible = set(self.pool.eligible)
        return sorted(
            (c for c in self.pool.chunks.values() if c["section_id"] == section_id and c["chunk_id"] in eligible),
            key=lambda c: (c["source_start"], c["chunk_id"]),
        )


def _where(chunk: dict) -> str:
    return f"{chunk['document_title']} / {chunk['heading_path']} (status {chunk.get('publication_status')})"


def make_tools(ctx: RunContext) -> dict[str, StructuredTool]:
    def search_policies(query: str, modes: str = "hybrid_rerank") -> str:
        """Search the selected policy corpus. modes: comma-separated, from vector, keyword, hybrid, hybrid_rerank, graph_rerank. Returns the top sections with short excerpts and section references such as S1."""
        requested = modes.replace(",", " ").split() if isinstance(modes, str) else list(modes or [])
        chosen = [m for m in requested if isinstance(m, str) and m in MODES][:2] or ["hybrid_rerank"]
        lines = []
        for mode in chosen:
            result = search_pool(ctx.session, ctx.index, ctx.pool, ctx.embedder, query, mode=mode, k=FINAL_K, reranker=ctx.reranker)
            ctx.searches.append({"query": query, "mode": mode, "chunk_ids": [h["chunk_id"] for h in result["hits"]],
                                 "graph": result["search"]["stages"].get("graph")})
            lines.append(f"mode {mode}:")
            for hit in result["hits"]:
                ctx.register(hit["chunk_id"])
                excerpt = " ".join(hit["text"].split())[:EXCERPT_CHARS]
                lines.append(f"- {ctx.ref(hit['section_id'])} rank {hit['rank']}: {_where(hit)}\n  {excerpt}")
        return "\n".join(lines) if lines else "No results."

    def get_section(section_id: str) -> str:
        """Return the full text of one section of the selected corpus, by reference (for example S2)."""
        sid = ctx.section_id(section_id)
        chunks = ctx.section_chunks(sid) if sid else []
        if not chunks:
            return f"No eligible section {section_id!r} in this corpus."
        for chunk in chunks:
            ctx.register(chunk["chunk_id"])
        text = "\n".join(c["text"].strip() for c in chunks)
        return f"{ctx.ref(sid)}: {_where(chunks[0])}\n{text[:SECTION_CHARS]}"

    def follow_policy_links(seed_ids: list[str], allowed_relation_types: list[str] | None = None) -> str:
        """Follow validated graph links one hop from sections (for example ["S1"]). allowed_relation_types: any of REFERENCES, APPLIES_TO_ROLE, MAPS_TO_CONTROL (default REFERENCES). Returns linked sections, roles, and controls with the source sentence of each link."""
        types = [t for t in (allowed_relation_types or ["REFERENCES"]) if t in RELATION_TYPES] or ["REFERENCES"]
        lines = []
        for seed in seed_ids[:5]:
            sid = ctx.section_id(seed)
            if sid is None:
                lines.append(f"{seed}: unknown section")
                continue
            rows = ctx.session.run(
                "MATCH (s:Section {generation_id: $g, section_id: $sid})-[r]->(t) WHERE type(r) IN $types "
                "RETURN type(r) AS type, properties(r) AS r, t.policy_id AS policy_id, t.name AS name, t.concept_id AS concept_id "
                "ORDER BY type, policy_id, name",
                g=ctx.pool.generation["id"], sid=sid, types=types,
            ).data()
            if not rows:
                lines.append(f"{ctx.ref(sid)}: no {', '.join(types)} links")
            for row in rows:
                edge = row["r"]
                path = {"from_section_id": sid, "edge": row["type"], "validation_status": edge["validation_status"],
                        "evidence": edge["evidence"], "source_span": [edge["source_start"], edge["source_end"]],
                        "source_document_version_id": edge["document_version_id"]}
                if row["type"] == "REFERENCES":
                    targets = sorted(
                        {c["section_id"] for c in ctx.pool.chunks.values()
                         if c["policy_id"] == row["policy_id"] and c["chunk_id"] in set(ctx.pool.eligible)
                         and (edge.get("target_section") is None or section_number(c["heading_path"]) == edge.get("target_section"))}
                    )
                    path.update(target_policy_id=row["policy_id"], target_section=edge.get("target_section"), target_section_ids=targets)
                    names = ", ".join(f"{ctx.ref(t)} {ctx.section_chunks(t)[0]['heading_path']}" for t in targets) or "no eligible section"
                    section = edge.get("target_section")
                    lines.append(f"{ctx.ref(sid)} REFERENCES {row['policy_id']}{' section ' + section if section else ''}: "
                                 f"{names}\n  because: {edge['evidence']}")
                else:
                    path.update(target=row["concept_id"], target_name=row["name"])
                    lines.append(f"{ctx.ref(sid)} {row['type']} {row['name']}\n  because: {edge['evidence']}")
                ctx.paths.append(path)
        return "\n".join(lines)

    def compare_versions(policy_id: str) -> str:
        """List every version of a policy in this snapshot with its status and effective dates, and which sections differ between versions."""
        chunks = [c for c in ctx.pool.chunks.values() if c["policy_id"] == policy_id.strip()]
        if not chunks:
            return f"No policy {policy_id!r} in this corpus."
        excluded = {e["chunk_id"]: e["reason"] for e in ctx.pool.excluded}
        versions: dict[str, dict] = {}
        for c in sorted(chunks, key=lambda c: (c["version"], c["source_start"])):
            v = versions.setdefault(c["version"], {"status": c.get("publication_status"), "from": c.get("effective_from"),
                                                   "to": c.get("effective_to"), "sections": {}, "excluded": excluded.get(c["chunk_id"])})
            v["sections"].setdefault(c["heading_path"], []).append(c["text"].strip())
        lines = []
        for version, v in versions.items():
            state = f"excluded here: {v['excluded']}" if v["excluded"] else "eligible"
            lines.append(f"version {version}: status {v['status']}, effective {v['from']} to {v['to'] or 'open'} ({state})")
        if len(versions) > 1:
            (a, va), (b, vb) = list(versions.items())[:2]
            for heading in sorted(set(va["sections"]) | set(vb["sections"])):
                if va["sections"].get(heading) != vb["sections"].get(heading):
                    lines.append(f"section {heading!r} differs between version {a} and {b}")
        else:
            lines.append("only one version is in this snapshot")
        return "\n".join(lines)

    return {
        fn.__name__: StructuredTool.from_function(fn)
        for fn in (search_policies, get_section, follow_policy_links, compare_versions)
    }
