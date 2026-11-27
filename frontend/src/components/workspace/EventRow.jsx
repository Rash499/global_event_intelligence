import { Badge, Meter } from "./primitives.jsx";
import {
  confidenceBand,
  eventState,
  formatNumber,
  severityBand,
  severityColour,
} from "../../services/format.jsx";
import { formatRelativeTime } from "../../services/dateFormat.jsx";

/**
 * A single event in list/queue form.
 *
 * Severity (how bad), confidence (how well evidenced) and priority (how urgently
 * an analyst should look) are shown as three separate things, never merged into
 * one "score".
 */
export default function EventRow({ event, onSelect, showCategory = true }) {
  const severity = severityBand(event.severity);
  const confidence = confidenceBand(event.confidence);
  const state = eventState(event.event_state);
  const label = event.severity_label || severity?.label;

  return (
    <article className="ws-event-row">
      <span
        className="ws-event-rail"
        style={{ background: severityColour(event.severity) }}
        aria-hidden="true"
      />
      <div className="ws-event-main">
        <div className="ws-event-title">
          <button type="button" className="ws-link" onClick={() => onSelect?.(event)}>
            {event.title || "Untitled event"}
          </button>
          {state.tone !== "muted" && <Badge tone={state.tone}>{state.label}</Badge>}
        </div>
        <div className="ws-event-meta">
          {showCategory && event.category && <span>{event.category.replace(/_/g, " ")}</span>}
          {event.subcategory && <span>{event.subcategory.replace(/_/g, " ")}</span>}
          <span>{event.country || "Location unresolved"}</span>
          <span>{formatRelativeTime(event.occurred_at || event.event_time, "time unknown")}</span>
          {event.corroboration_level && (
            <span title="Independent publishers after syndication detection">
              {event.corroboration_level.replace(/_/g, " ")}
            </span>
          )}
        </div>
      </div>

      <div className="ws-event-scores">
        <div className="ws-score">
          <span className="ws-score-label">Severity</span>
          <strong style={{ color: severityColour(event.severity) }}>
            {event.severity === null || event.severity === undefined
              ? "n/a"
              : formatNumber(event.severity, 1)}
          </strong>
          <span className="ws-score-sub">{label || "not assessed"}</span>
        </div>
        <div className="ws-score">
          <span className="ws-score-label">Confidence</span>
          <strong style={{ color: confidence?.colour }}>
            {event.confidence === null || event.confidence === undefined
              ? "n/a"
              : `${Math.round(Number(event.confidence) * 100)}%`}
          </strong>
          <span className="ws-score-sub">
            {event.corroboration?.independent_publishers ?? event.independent_source_count ?? 0} indep. source
            {(event.corroboration?.independent_publishers ?? event.independent_source_count ?? 0) === 1 ? "" : "s"}
          </span>
        </div>
        <div className="ws-score">
          <span className="ws-score-label">Priority</span>
          <strong>{event.priority_label || "—"}</strong>
          <Meter
            value={event.priority_score || 0}
            max={10}
            colour="#8b7cff"
            label="Operational priority"
          />
        </div>
      </div>
    </article>
  );
}
