import {
  formatCategory,
  formatDate,
  getImportanceLabel,
} from "./eventDetailsUtils";

export default function EventHeader({ details, loading, onBack }) {
  const importanceLabel = getImportanceLabel(details.importance);

  return (
    <>
      <div className="detail-topbar">
        <button className="back-button" onClick={onBack}>
          <span aria-hidden="true">←</span> Back to events
        </button>

        <span className="detail-status">
          <span className="detail-status-dot" />
          Intelligence brief
        </span>
      </div>

      <header className="detail-header">
        <div className="detail-heading-row">
          <span className="badge">{formatCategory(details.category)}</span>
          <span className={`severity severity-${importanceLabel.toLowerCase()}`}>
            {importanceLabel} impact
          </span>
          {details.credibility_score != null && (
            <span className="badge credibility-badge" title="Ranks catalogued source metadata and independent corroboration; it does not judge truth.">
              Source credibility {details.credibility_score}/100
            </span>
          )}
        </div>

        <h2>{details.title || "Untitled event"}</h2>

        <div className="detail-byline">
          <span>{details.country || "Global"}</span>
          <span aria-hidden="true">•</span>
          <span>{formatDate(details.event_time)}</span>
          {loading && <span className="detail-refreshing">Updating details...</span>}
        </div>
      </header>

      <p className="detail-summary">
        {details.summary || "No summary is available for this event yet."}
      </p>
    </>
  );
}
