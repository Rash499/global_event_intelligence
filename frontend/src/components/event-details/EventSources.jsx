export default function EventSources({ sources, loading }) {
  return (
    <div className="sources-section">
      <div className="sources-heading">
        <div>
          <span className="section-eyebrow">Evidence trail</span>
          <h3>News sources</h3>
        </div>
        <span className="source-count">{sources.length}</span>
      </div>

      {loading ? (
        <div className="sources-loading" role="status">
          <span className="loading-pulse" /> Loading source records...
        </div>
      ) : sources.length ? (
        <div className="sources-list">
          {sources.map((source, index) => (
            <a
              key={source.url || `${source.title}-${index}`}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="source-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="source-copy">
                <strong>{source.title || "Untitled source"}</strong>
                <small>{source.source || "Unknown publisher"}</small>
              </span>
              <span className="source-arrow" aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      ) : (
        <div className="sources-empty">
          <strong>No source information available</strong>
          <span>This event does not have linked reporting yet.</span>
        </div>
      )}
    </div>
  );
}
