import { useEffect, useMemo, useState } from "react";

import { getEvent } from "../../services/api.jsx";
import { formatDateTime, formatRelativeTime } from "../../services/dateFormat.jsx";
import {
  breakdownRows,
  confidenceBand,
  eventState,
  formatCount,
  formatNumber,
  locationPrecision,
  priorityMeta,
  severityBand,
  severityColour,
} from "../../services/format.jsx";
import { Badge, Breakdown, Empty, ErrorState, Explain, Loading, Meter, Panel, SourceNote } from "./primitives.jsx";

const SEVERITY_LABELS = {
  physical_magnitude: "Physical magnitude",
  casualties: "Reported casualties",
  geographic_scale: "Geographic scale",
  disruption: "Disruption",
  duration: "Duration",
  baseline: "Category baseline",
  official_alert: "Official alert level",
  infrastructure: "Infrastructure damage",
};

const CONFIDENCE_LABELS = {
  independent_sources: "Independent sources",
  source_tier: "Source tier",
  official_confirmation: "Official confirmation",
  structured_observation: "Structured observation",
  language_coverage: "Language coverage",
  precision_bonus: "Location precision",
  base: "Base reliability",
  syndication_penalty: "Syndicated copies (penalty)",
  single_source_penalty: "Single source (penalty)",
  ambiguity_penalty: "Ambiguous reporting (penalty)",
};

/** Time precision is a real property of the data and is labelled, not hidden. */
function timeBlock(event) {
  return [
    { label: "Occurred", value: event.occurred_at, precision: event.occurred_at_precision || event.event_time_precision },
    { label: "Observed by sensors", value: event.observed_at },
    { label: "Published", value: event.event_time, precision: event.event_time_precision },
    { label: "First ingested", value: event.first_seen_at },
    { label: "Last seen", value: event.last_seen_at },
    { label: "Assessment updated", value: event.assessment_updated_at },
  ].filter((row) => row.value);
}

export default function EventInvestigation({ eventId, initialEvent, onBack, onSelectEvent, onOpenCountry }) {
  const [event, setEvent] = useState(initialEvent || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getEvent(eventId)
      .then((data) => {
        if (!cancelled) setEvent(data);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const severity = severityBand(event?.severity);
  const confidence = confidenceBand(event?.confidence);
  const state = eventState(event?.event_state);
  const priority = priorityMeta(event?.priority_label);
  const precision = locationPrecision(event?.location_precision || event?.location?.precision);

  const independentSources = useMemo(
    () => (event?.sources || []).filter((source) => source.is_independent !== 0),
    [event]
  );
  const syndicatedSources = useMemo(
    () => (event?.sources || []).filter((source) => source.is_independent === 0),
    [event]
  );
  const publishers = useMemo(
    () => new Set((event?.sources || []).map((source) => source.publisher_domain || source.publisher).filter(Boolean)),
    [event]
  );

  if (loading && !event) return <Loading label="Loading event evidence" />;
  if (error) return <ErrorState error={error} title="Event could not be loaded" />;
  if (!event) return <Empty title="Event not found">The event may have been purged by the retention policy.</Empty>;

  return (
    <div className="ws-view ws-investigation">
      <header className="ws-view-head">
        <button type="button" className="ws-back" onClick={onBack}>← Back</button>
        <div className="ws-title-block">
          <p className="eyebrow">
            INVESTIGATION · EVENT #{event.id}
            {event.is_structured_observation ? " · STRUCTURED SENSOR OBSERVATION" : ""}
          </p>
          <h1>{event.title}</h1>
          <div className="ws-chip-row">
            <Badge tone={state.tone}>{state.label}</Badge>
            {event.category && <Badge>{event.category.replace(/_/g, " ")}</Badge>}
            {event.subcategory && <Badge>{event.subcategory.replace(/_/g, " ")}</Badge>}
            {event.taxonomy_version && <Badge>taxonomy v{event.taxonomy_version}</Badge>}
            {event.classification_method && <Badge>classified: {event.classification_method.replace(/_/g, " ")}</Badge>}
          </div>
        </div>
      </header>

      <div className="ws-score-strip">
        <div className="ws-score-card">
          <span>Severity</span>
          <strong style={{ color: severityColour(event.severity) }}>
            {event.severity == null ? "not assessed" : formatNumber(event.severity, 1)}
          </strong>
          <span className="ws-muted">{event.severity_label || severity?.label || "no evidence for a band"}</span>
        </div>
        <div className="ws-score-card">
          <span>Intelligence confidence</span>
          <strong style={{ color: confidence?.colour }}>
            {event.confidence == null ? "not assessed" : `${Math.round(Number(event.confidence) * 100)}%`}
          </strong>
          <span className="ws-muted">{confidence?.label || "no evidence"}</span>
        </div>
        <div className="ws-score-card">
          <span>Operational priority</span>
          <strong style={{ color: priority.colour }}>{event.priority_label || "—"}</strong>
          <Meter value={event.priority_score || 0} max={10} colour={priority.colour} label="Priority score" />
        </div>
        <div className="ws-score-card">
          <span>Corroboration</span>
          <strong>{formatNumber(event.independent_source_count || 0)}</strong>
          <span className="ws-muted">
            independent · {formatNumber(event.syndicated_source_count || 0)} syndicated
          </span>
        </div>
      </div>

      <div className="ws-grid-2">
        <Panel title="Assessment" eyebrow="STORED INTELLIGENCE">
          <p className="ws-body-text">{event.summary || "No summary was stored for this event."}</p>
          {event.ai_assessment && (
            <div className="ws-ai-note">
              <strong>AI-generated assessment — not verified fact</strong>
              <p>{event.ai_assessment}</p>
              <span className="ws-muted">
                {event.ai_model || "model unknown"}
                {event.ai_assessment_at ? ` · ${formatDateTime(event.ai_assessment_at)}` : ""}
              </span>
            </div>
          )}
          <Explain summary="Why this severity" defaultOpen>
            <Breakdown components={event.severity_components} labels={SEVERITY_LABELS} max={10} />
            <SourceNote>
              Severity reflects reported impact and physical measurements. It is not a probability and it is not
              comparable across categories as a single scale — use it with the category and coverage figures.
            </SourceNote>
          </Explain>
          <Explain summary="Why this confidence">
            <Breakdown components={event.confidence_components} labels={CONFIDENCE_LABELS} max={1} />
            {event.confidence_explanation && <p className="ws-body-text">{event.confidence_explanation}</p>}
            <SourceNote>
              Syndicated copies of the same wire story count once. Confidence grows with independent publishers, not
              with article volume.
            </SourceNote>
          </Explain>
          {event.escalation_trend && (
            <p className="ws-inline-note">
              <strong>Trend:</strong> {event.escalation_trend.replace(/_/g, " ")}
            </p>
          )}
        </Panel>

        <div className="ws-stack">
          <Panel title="Location" eyebrow="WHERE">
            <dl className="ws-facts">
              <div><dt>Country</dt><dd>{event.country || "unresolved"}{event.country_code ? ` (${event.country_code})` : ""}</dd></div>
              <div><dt>Precision</dt><dd>{precision.label}</dd></div>
              <div><dt>Location text</dt><dd>{event.location_text || "not extracted"}</dd></div>
              <div>
                <dt>Coordinates</dt>
                <dd>
                  {event.latitude != null && event.longitude != null
                    ? `${formatNumber(event.latitude, 3)}, ${formatNumber(event.longitude, 3)}`
                    : "none reported"}
                </dd>
              </div>
              {event.geocoding_source && <div><dt>Geocoded by</dt><dd>{event.geocoding_source}</dd></div>}
            </dl>
            {!precision.plottable && (
              <SourceNote tone="warn">
                This event is known only at {precision.label.toLowerCase()} level, so it is shown as a country/region
                indicator rather than a map pin. Plotting it as a point would invent a location.
              </SourceNote>
            )}
            {event.country_code && onOpenCountry && (
              <button
                type="button"
                className="ws-button"
                onClick={() => onOpenCountry({ code: event.country_code, name: event.country })}
              >
                Open country intelligence
              </button>
            )}
          </Panel>

          <Panel title="Timeline" eyebrow="EVENT TIME VS PUBLICATION VS INGESTION">
            <dl className="ws-facts">
              {timeBlock(event).map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>
                    {formatDateTime(row.value)}
                    {row.precision && row.precision !== "exact" && (
                      <Badge tone="warn">{row.precision.replace(/_/g, " ")}</Badge>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            {(event.timeline || []).length > 0 && (
              <ol className="ws-timeline">
                {event.timeline.map((entry, index) => (
                  <li key={`${entry.occurred_at}-${index}`}>
                    <span className="ws-timeline-time">{formatDateTime(entry.occurred_at)}</span>
                    <span className="ws-timeline-body">
                      <strong>{String(entry.change_type || "update").replace(/_/g, " ")}</strong>
                      {entry.description ? ` — ${entry.description}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>

      <Panel
        title="Sources"
        eyebrow={`${formatCount(independentSources.length, "independent source")} · ${formatCount(
          syndicatedSources.length,
          "syndicated copy",
          "syndicated copies"
        )} · ${formatCount(publishers.size, "publisher")}`}
      >
        {(event.sources || []).length === 0 ? (
          <Empty title="No stored articles">This event has no linked reporting. It may come from a structured feed only.</Empty>
        ) : (
          <ul className="ws-source-list">
            {event.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title || source.url}</a>
                <div className="ws-source-meta">
                  <span>{source.publisher || source.publisher_domain || "unknown publisher"}</span>
                  {source.provider && <span className="ws-muted">via {source.provider}</span>}
                  {source.reporting_type && <Badge>{source.reporting_type.replace(/_/g, " ")}</Badge>}
                  {source.is_independent === 0 && <Badge tone="warn">syndicated</Badge>}
                  {source.syndication_of && <span className="ws-muted">of {source.syndication_of}</span>}
                  <span className="ws-muted">{source.published_at ? formatRelativeTime(source.published_at) : "publication time unknown"}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="ws-grid-2">
        <Panel title="Relationships" eyebrow="RELATED EVENTS">
          {(event.relationships || []).length === 0 ? (
            <Empty title="No linked events">
              Related events are derived from shared anchors, geography and time. An empty list means no match was
              found in the stored window, not that nothing else happened.
            </Empty>
          ) : (
            <ul className="ws-relationship-list">
              {event.relationships.map((relation) => (
                <li key={`${relation.event_id}-${relation.relationship}`}>
                  <Badge>{relation.relationship.replace(/_/g, " ")}</Badge>
                  <button
                    type="button"
                    className="ws-link"
                    onClick={() => onSelectEvent?.({ id: relation.event_id })}
                  >
                    {relation.title}
                  </button>
                  <span className="ws-muted">
                    {relation.relationship} · match {formatNumber((relation.confidence || 0) * 100, 0)}%
                    {relation.reason ? ` · ${relation.reason}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Entities" eyebrow="ACTORS MENTIONED">
          {(event.entities || []).length === 0 ? (
            <Empty title="No entities extracted">Entity extraction runs during assessment; none were stored for this event.</Empty>
          ) : (
            <ul className="ws-entity-list">
              {event.entities.map((entity) => (
                <li key={entity.id}>
                  <strong>{entity.name}</strong>
                  <span className="ws-muted">{entity.entity_type}</span>
                  {entity.role && <Badge>{entity.role}</Badge>}
                  <span className="ws-muted">match {formatNumber((entity.confidence || 0) * 100, 0)}%</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {(event.provider_keys || event.data_sources) && (
        <SourceNote>
          Collected from: {Array.isArray(event.provider_keys) ? event.provider_keys.join(", ") : event.provider_keys}
          {Array.isArray(event.data_sources) && event.data_sources.length ? ` · ${event.data_sources.join(", ")}` : ""}
        </SourceNote>
      )}
    </div>
  );
}
