import {
  getConfidence,
  getImportanceLabel,
} from "./eventDetailsUtils";

export default function EventMetrics({ details, sourceCount }) {
  const importanceLabel = getImportanceLabel(details.importance);
  const confidence = getConfidence(details.confidence);

  return (
    <div className="detail-grid">
      <div className="detail-metric">
        <span>Importance</span>
        <strong className={`metric-value metric-${importanceLabel.toLowerCase()}`}>
          {details.importance ?? 0}<small>/10</small>
        </strong>
        <em>{importanceLabel} impact</em>
      </div>

      <div className="detail-metric">
        <span>Confidence</span>
        <strong>{confidence}</strong>
        <div className="confidence-track" aria-label={`Confidence ${confidence}`}>
          <span style={{ width: confidence }} />
        </div>
      </div>

      <div className="detail-metric">
        <span>Country</span>
        <strong>{details.country || "Global"}</strong>
        <em>{details.country_code || "Worldwide"}</em>
      </div>

      <div className="detail-metric">
        <span>Sources</span>
        <strong>{sourceCount}</strong>
        <em>{sourceCount === 1 ? "reported source" : "reported sources"}</em>
      </div>
    </div>
  );
}
