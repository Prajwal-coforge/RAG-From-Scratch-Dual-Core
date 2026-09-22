"""Policy RAG: Coforge PDFs → section chunks → hybrid retrieve."""

__all__ = ["ingest_chunks", "retrieve"]


def __getattr__(name: str):
    if name in {"ingest_chunks", "retrieve"}:
        from policy_rag import pipeline

        return getattr(pipeline, name)
    raise AttributeError(name)
