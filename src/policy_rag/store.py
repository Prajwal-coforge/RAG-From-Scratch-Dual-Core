from __future__ import annotations

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from policy_rag.config import CHROMA_DIR, COLLECTION_NAME


def get_client(path: str | None = None) -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path or CHROMA_DIR))


def get_collection(
    client: chromadb.PersistentClient | None = None,
    name: str | None = None,
    reset: bool = False,
) -> Collection:
    client = client or get_client()
    coll_name = name or COLLECTION_NAME
    if reset:
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass
    return client.get_or_create_collection(name=coll_name, metadata={"hnsw:space": "cosine"})


def upsert_chunks(
    collection: Collection,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]],
) -> None:
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def query_vector(
    collection: Collection,
    query_embedding: list[float],
    n_results: int,
) -> dict[str, Any]:
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )


def all_records(collection: Collection) -> dict[str, Any]:
    return collection.get(include=["documents", "metadatas"])
