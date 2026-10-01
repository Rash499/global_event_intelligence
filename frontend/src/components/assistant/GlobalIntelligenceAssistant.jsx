import { useCallback, useEffect, useRef, useState } from "react";

import {
  askAssistant,
  getAssistantStatus,
  getAssistantSuggestions,
  runAssistantIndexing,
} from "../../services/api.jsx";

const STATUS_TONES = {
  ok: "ok",
  insufficient_data: "warn",
  out_of_scope: "warn",
  llm_unavailable: "error",
  retrieval_unavailable: "error",
  disabled: "error",
  error: "error",
};

function statusLabel(status) {
  switch (status) {
    case "ok":
      return "Grounded answer";
    case "insufficient_data":
      return "Not enough data";
    case "out_of_scope":
      return "Out of scope";
    case "llm_unavailable":
      return "AI model offline";
    case "retrieval_unavailable":
      return "Search index offline";
    case "disabled":
      return "Assistant disabled";
    default:
      return "Request failed";
  }
}

function formatTime(iso) {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString();
}

export default function GlobalIntelligenceAssistant({ onBack }) {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [indexNote, setIndexNote] = useState("");
  const scrollRef = useRef(null);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await getAssistantStatus());
      setStatusError("");
    } catch (error) {
      console.error(error);
      setStatusError("Assistant status is unavailable. Is the backend running?");
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    try {
      const data = await getAssistantSuggestions();
      setSuggestions(data.suggestions || []);
    } catch (error) {
      console.error(error);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadSuggestions();
  }, [loadStatus, loadSuggestions]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, asking]);

  const sendQuestion = useCallback(
    async (question) => {
      const text = (question || "").trim();
      if (!text || asking) return;

      setDraft("");
      setMessages((previous) => [...previous, { role: "user", content: text }]);
      setAsking(true);

      try {
        const conversation = messages.slice(-6).map((message) => ({
          role: message.role,
          content: message.content,
        }));
        const result = await askAssistant({ question: text, conversation });
        setMessages((previous) => [
          ...previous,
          { role: "assistant", content: "", result },
        ]);
        loadStatus();
      } catch (error) {
        console.error(error);
        setMessages((previous) => [
          ...previous,
          {
            role: "assistant",
            content: "",
            result: {
              status: "error",
              message:
                "The request to the backend failed. Check that FastAPI is running on port 8000.",
              sources: [],
              evidence: [],
              validation_warnings: [],
            },
          },
        ]);
      } finally {
        setAsking(false);
      }
    },
    [asking, messages, loadStatus]
  );

  const reindex = useCallback(async () => {
    setIndexing(true);
    setIndexNote("");
    try {
      const result = await runAssistantIndexing();
      setIndexNote(
        `Index ${result.status}: ${result.indexed} indexed, ${result.skipped} skipped, ${result.failed} failed.`
      );
      loadStatus();
    } catch (error) {
      console.error(error);
      setIndexNote("Indexing request failed. Check the backend connection.");
    } finally {
      setIndexing(false);
    }
  }, [loadStatus]);

  const notice =
    statusError ||
    (!status?.enabled
      ? "The assistant is disabled on this deployment (RAG_ENABLED=false)."
      : "");
  return (
    <main className="assistant-page">
      <div className="dashboard-navigation">
        <button className="back-button" onClick={onBack}>
          ← Back to World Map
        </button>
      </div>

      <header className="assistant-header">
        <p className="eyebrow">PHASE 3 · RAG ASSISTANT</p>
        <h2>Global Intelligence Assistant</h2>
        <p className="assistant-subtitle">
          Ask questions about the events and articles collected by this platform.
          Answers are grounded in retrieved database records and cite their
          sources. Importance and confidence values are application-derived
          scores, not official assessments.
        </p>
      </header>

      <section className="assistant-status" aria-label="Assistant status">
        {notice && <div className="notice assistant-notice">{notice}</div>}
        {status && (
          <div className="assistant-status-grid">
            <span
              className={
                status.llm_available ? "assistant-chip ok" : "assistant-chip error"
              }
            >
              AI model:{" "}
              {status.llm_available
                ? `${status.chat_model} ready`
                : "offline (Ollama)"}
            </span>
            <span
              className={
                status.embedding_available
                  ? "assistant-chip ok"
                  : "assistant-chip error"
              }
            >
              Embeddings:{" "}
              {status.embedding_available
                ? `${status.embedding_provider} · ${status.embedding_model}`
                : "unavailable"}
            </span>
            <span
              className={
                status.vector_store_available
                  ? "assistant-chip ok"
                  : "assistant-chip error"
              }
            >
              Search index:{" "}
              {status.vector_store_available ? status.vector_store : "unavailable"}
            </span>
            <span className="assistant-chip">
              Indexed: {status.indexed_documents} documents
              {status.pending_documents > 0
                ? ` (${status.pending_documents} pending)`
                : ""}
            </span>
            <button
              type="button"
              className="assistant-reindex"
              onClick={reindex}
              disabled={indexing}
            >
              {indexing ? "Indexing..." : "Re-index database"}
            </button>
          </div>
        )}
        {indexNote && <div className="assistant-index-note">{indexNote}</div>}
      </section>

      {suggestions.length > 0 && messages.length === 0 && (
        <section className="assistant-suggestions" aria-label="Suggested questions">
          {suggestions.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => sendQuestion(item.question)}
              disabled={asking}
            >
              {item.label}
            </button>
          ))}
        </section>
      )}

      <section className="assistant-thread" ref={scrollRef} aria-live="polite">
        {messages.length === 0 && !asking && (
          <div className="assistant-empty">
            <strong>No questions yet</strong>
            <span>
              Try one of the suggestions above, or type a question such as
              &ldquo;What major natural disasters happened this week?&rdquo;
            </span>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <article key={`user-${index}`} className="assistant-message user">
              <span className="assistant-role">You asked</span>
              <p>{message.content}</p>
            </article>
          ) : (
            <AssistantReply key={`assistant-${index}`} message={message} />
          )
        )}

        {asking && (
          <article className="assistant-message pending" role="status">
            <span className="assistant-role">Assistant</span>
            <p>Retrieving records and generating a grounded answer...</p>
          </article>
        )}
      </section>

      <form
        className="assistant-composer"
        onSubmit={(event) => {
          event.preventDefault();
          sendQuestion(draft);
        }}
      >
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask about recent events, countries, categories..."
          maxLength={500}
          aria-label="Question for the assistant"
        />
        <button type="submit" disabled={asking || !draft.trim()}>
          {asking ? "Thinking..." : "Ask"}
        </button>
      </form>
    </main>
  );
}
function AssistantReply({ message }) {
  const result = message.result || {};
  const tone = STATUS_TONES[result.status] || "warn";
  const answer =
    result.answer ||
    result.message ||
    "No answer was produced for this question.";
  const evidence = result.evidence || [];
  const sources = result.sources || [];
  const warnings = result.validation_warnings || [];
  const retrieval = result.retrieval;

  return (
    <article className={`assistant-message assistant tone-${tone}`}>
      <span className="assistant-role">
        Assistant · {statusLabel(result.status)}
        {typeof result.grounded === "boolean" && result.status === "ok" && (
          <em className={result.grounded ? "grounded yes" : "grounded no"}>
            {result.grounded ? "grounded in records" : "not fully grounded"}
          </em>
        )}
        {result.llm_model && <em className="model-tag">{result.llm_model}</em>}
      </span>

      <p className="assistant-answer">{answer}</p>

      {warnings.length > 0 && (
        <ul className="assistant-warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      {result.metrics && (
        <div className="assistant-metrics" aria-label="Platform-computed metrics">
          <span>
            <strong>{result.metrics.matching_events}</strong> matching events
          </span>
          <span>
            <strong>{result.metrics.major_events}</strong> major (importance ≥ 7)
          </span>
          {result.metrics.countries?.slice(0, 3).map((entry) => (
            <span key={entry.country || entry.country_code}>
              <strong>{entry.count}</strong> {entry.country || entry.country_code}
            </span>
          ))}
          <span className="assistant-metrics-note">
            platform SQL aggregates · application-derived
          </span>
        </div>
      )}

      {retrieval && (
        <div className="assistant-retrieval">
          <span>retrieval: {retrieval.mode}</span>
          <span>relevance: {retrieval.relevance}</span>
          <span>records: {result.retrieved_count}</span>
          {result.elapsed_ms ? (
            <span>{(result.elapsed_ms / 1000).toFixed(1)}s</span>
          ) : null}
        </div>
      )}
      {evidence.length > 0 && (
        <details className="assistant-evidence" open>
          <summary>
            Retrieved records ({evidence.length}) — event confidence is an
            application score
          </summary>
          <ol>
            {evidence.map((record) => (
              <li
                key={`${record.record_number}-${record.event_id ?? record.title}`}
              >
                <div className="evidence-head">
                  <span className="evidence-record">[{record.record_number}]</span>
                  <strong>{record.title}</strong>
                </div>
                <div className="evidence-meta">
                  {record.category && <span>{record.category}</span>}
                  {record.country && <span>{record.country}</span>}
                  {record.event_time && <span>{formatTime(record.event_time)}</span>}
                  {record.importance != null && (
                    <span>importance {record.importance}/10 (app score)</span>
                  )}
                  {record.confidence != null && (
                    <span>
                      event confidence{" "}
                      {Number(record.confidence).toFixed(2)} (app score)
                    </span>
                  )}
                  {record.corroboration_level && (
                    <span>{record.corroboration_level}</span>
                  )}
                  <span className="evidence-relevance">
                    relevance {Number(record.relevance).toFixed(2)} ·{" "}
                    {record.matched_on}
                  </span>
                </div>
                {record.summary && <p>{record.summary}</p>}
              </li>
            ))}
          </ol>
        </details>
      )}

      {sources.length > 0 && (
        <div className="assistant-sources" aria-label="Sources from the database">
          <h4>Sources (from platform database)</h4>
          <ul>
            {sources.map((source, index) => (
              <li key={`${source.url || source.title}-${index}`}>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                    {source.title || source.source || source.url}
                  </a>
                ) : (
                  <span>{source.title || source.source || "Untitled source"}</span>
                )}
                <small>
                  {source.source || "Unknown publisher"}
                  {source.published_at ? ` · ${formatTime(source.published_at)}` : ""}
                  {source.verified_in_database ? " · verified in DB" : ""}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}



