"""Policy RAG: Coforge PDFs → section chunks → hybrid retrieve → Qwen / stub."""

__all__ = ["answer_question"]


def __getattr__(name: str):
    if name == "answer_question":
        from policy_rag.pipeline import answer_question

        return answer_question
    raise AttributeError(name)
