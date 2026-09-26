import { useState } from "react";

const STATUS_LABEL = {
  answered: "Answered",
  needs_clarification: "Needs clarification",
  insufficient_evidence: "Insufficient evidence",
  conflicting_sources: "Conflicting sources",
  unavailable: "Unavailable",
};

export function App() {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [openCitation, setOpenCitation] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    setPending(true);
    setOpenCitation(null);
    setResult(null);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          corpus_id: null,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setResult({
          answer: { status: "unavailable", answer: body.detail || "The answer service is unavailable.", citations: [], follow_up_questions: [] },
          trace: null,
          triage: null,
        });
        return;
      }
      setResult(body);
    } catch {
      setResult({
        answer: { status: "unavailable", answer: "The answer service is unavailable.", citations: [], follow_up_questions: [] },
        trace: null,
        triage: null,
      });
    } finally {
      setPending(false);
    }
  }

  const answer = result?.answer;
  const status = answer?.status;

  return (
    <main>
      <header className="brand">
        <svg className="mark" viewBox="0 0 48 48" aria-hidden="true">
          <rect x="16" y="7" width="20" height="28" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <rect x="11" y="12" width="20" height="28" fill="#f7f4ef" stroke="currentColor" strokeWidth="1.5" />
          <path d="M15 20h12M15 25h9" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        <div>
          <h1>Airport Policy Assistant</h1>
          <p>Ask a policy question. Answers use the latest published version in force.</p>
        </div>
      </header>
      <form onSubmit={onSubmit}>
        <label htmlFor="question">Question</label>
        <textarea id="question" required maxLength={2000} value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button type="submit" disabled={pending || !question.trim()}>
          {pending ? "Asking…" : "Ask"}
        </button>
      </form>
      {answer ? (
        <section aria-live="polite">
          <p className={`status status-${status}`}>{STATUS_LABEL[status] || status}</p>
          <h2>Answer</h2>
          <p>{answer.answer}</p>
          {(answer.follow_up_questions || []).map((followUp) => (
            <p key={followUp}>{followUp}</p>
          ))}
          <h2>Citations</h2>
          {(answer.citations || []).length === 0 ? <p>No citations.</p> : null}
          <ul>
            {(answer.citations || []).map((citation) => (
              <li key={citation.citation_id}>
                <button type="button" onClick={() => setOpenCitation(citation)}>
                  [{citation.citation_id}] {citation.document_title} / {citation.section_path}
                </button>
              </li>
            ))}
          </ul>
          {result.trace ? <Trace trace={result.trace} /> : null}
        </section>
      ) : null}
      {openCitation ? <CitationDrawer citation={openCitation} onClose={() => setOpenCitation(null)} /> : null}
    </main>
  );
}

function Trace({ trace }) {
  const graph = trace.search?.stages?.graph;
  return (
    <details>
      <summary>Explain retrieval</summary>
      <p>
        Mode {trace.mode}. Generation {trace.index_generation_id}. In force {trace.as_of}
        {trace.as_of_basis ? ` (${trace.as_of_basis})` : ""}. Retrieval {trace.timing_ms} ms.
      </p>
      <p>{trace.search?.method}</p>
      {graph ? (
        <p>
          Graph {graph.edge}, {graph.hops} hop, {graph.edges_in_generation} validated edges, {graph.added?.length || 0} added.
        </p>
      ) : null}
      <ol>
        {trace.hits.map((hit) => (
          <li key={hit.chunk_id}>
            [{hit.rank}] {hit.document_title} / {hit.heading_path}
          </li>
        ))}
      </ol>
    </details>
  );
}

function CitationDrawer({ citation, onClose }) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-labelledby="citation-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="citation-title">{citation.document_title}</h2>
        <p>Version {citation.version}</p>
        <p>Section {citation.section_path}</p>
        <p>Resolved {citation.resolved ? "yes" : "no"}</p>
        <blockquote>{citation.excerpt}</blockquote>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </aside>
    </div>
  );
}
