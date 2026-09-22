from __future__ import annotations

from policy_rag.chunking import Chunk
from policy_rag.config import RERANK_K
from policy_rag.embeddings import embed_documents, embed_query
from policy_rag.rerank import rerank
from policy_rag.retrieve import Hit, hybrid_retrieve
from policy_rag.store import get_collection, upsert_chunks


def ingest_chunks(chunks: list[Chunk], reset: bool = False) -> int:
    if not chunks:
        return 0
    collection = get_collection(reset=reset)
    embeddings = embed_documents([c.text for c in chunks])
    upsert_chunks(
        collection,
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embeddings,
        metadatas=[c.metadata() for c in chunks],
    )
    return len(chunks)


def retrieve(
    question: str,
    rerank_top_k: int = RERANK_K,
    use_rerank: bool = True,
) -> list[Hit]:
    collection = get_collection()
    query_vec = embed_query(question)
    hits = hybrid_retrieve(collection, question, query_vec)
    if use_rerank:
        return rerank(question, hits, top_k=rerank_top_k)
    return hits[:rerank_top_k]
