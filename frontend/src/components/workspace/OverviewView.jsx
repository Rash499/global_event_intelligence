import { useCallback } from "react";

import { getAnomalies, getDashboardOverview } from "../../services/api.jsx";
import { formatRelativeTime } from "../../services/dateFormat.jsx";
import { formatCount, formatNumber, severityColour } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, ErrorState, Empty, Loading, Meter, Panel, Stat, UpdatedAt } from "./primitives.jsx";
import EventRow from "./EventRow.jsx";

const STATE_TONES = { new: "info", developing: "warn", escalating: "danger", stable: "ok" };

export default function OverviewView({ onSelectEvent, onNavigate, refreshMs = 60000 }) {
  const overview = useApiResource(() => getDashboardOverview(24), [], { pollMs: refreshMs });
  const anomalies = useApiResource(() => getAnomalies(), [], { pollMs: refreshMs * 2 });

  const data = overview.data;
  const totals = data?.totals || {};
  const distribution = (data?.severity_distribution || []).filter((band) => band.count > 0);
  const maxBand = Math.max(1, ...distribution.map((band) => band.count));

  const handleSelect = useCallback((event) => onSelectEvent?.({ id: event.id, event }), [onSelectEvent]);

  if (overview.loading && !data) return <Loading label="Loading workspace overview" />;
  if (overview.error) {
    return <ErrorState error={overview.error} onRetry={overview.reload} title="Overview unavailable" />;
  }

  return (
    <div className="ws-view ws-overview">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">OPERATIONS OVERVIEW</p>
          <h1>Global situation</h1>
          <p className="ws-subtitle">
            Counts come from stored events and articles. “Last ingestion” shows how fresh the picture is — an empty
            feed means nothing was collected, not that nothing happened.
          </p>
        </div>
        <div className="ws-head-meta">
          <UpdatedAt value={overview.updatedAt} loading={overview.loading} />
          <button type="button" className="ws-button" onClick={overview.reload}>Refresh</button>
        </div>
      </header>

      <div className="ws-stat-grid">
        <Stat label="Active events" value={totals.active_events} hint="not resolved or archived" />
        <Stat label="Events last 24h" value={totals.events_24h} hint="by occurrence time" />
        <Stat label="Critical severity" value={totals.critical_events} hint="≥ 8.5" tone="danger" />
        <Stat label="High confidence" value={totals.high_confidence_events} hint="≥ 0.75 evidence score" tone="ok" />
        <Stat label="Developing / escalating" value={totals.developing_events} tone="warn" />
        <Stat label="Countries affected" value={totals.countries_affected} />
        <Stat label="Open alerts" value={totals.active_alerts} tone={totals.active_alerts ? "warn" : "default"} />
        <Stat label="New alerts" value={(anomalies.data?.count ?? null)} hint="anomalies detected" tone="warn" />
      </div>

      <div className="ws-grid-3">
        <Panel title="Severity mix" eyebrow="ALL STORED EVENTS">
          {distribution.length === 0 ? (
            <Empty title="No assessed events yet">
              Events appear here once collection and assessment have run. Nothing is pre-filled.
            </Empty>
          ) : (
            <ul className="ws-bars">
              {distribution.map((band) => (
                <li key={band.label}>
                  <span className="ws-bar-label">{band.label}</span>
                  <div className="ws-bar-track">
                    <span
                      className="ws-bar-fill"
                      style={{ width: `${(band.count / maxBand) * 100}%`, background: severityColour(
                        { critical: 9, high: 7, moderate: 5, low: 3, minimal: 1, unknown: null }[band.label]
                      ) }}
                    />
                  </div>
                  <span className="ws-bar-value">{formatNumber(band.count)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Top countries" eyebrow="BY EVENT COUNT">
          {(data?.countries || []).length === 0 ? (
            <Empty title="No country attribution yet" />
          ) : (
            <ul className="ws-rank-list">
              {data.countries.slice(0, 8).map((country) => (
                <li key={country.country_code}>
                  <button type="button" className="ws-link" onClick={() => onNavigate?.("countries", { country: country.country_code })}>
                    {country.country || country.country_code}
                  </button>
                  <span className="ws-muted">{formatCount(country.event_count, "event")}</span>
                  {country.max_severity != null && (
                    <Badge colour={severityColour(country.max_severity)}>max {formatNumber(country.max_severity, 1)}</Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Source mix" eyebrow="ARTICLES BY PROVIDER">
          {(data?.source_mix || []).length === 0 ? (
            <Empty title="No articles collected yet">
              Configure providers in <code>backend/.env</code>, then run a collection.
            </Empty>
          ) : (
            <ul className="ws-rank-list">
              {data.source_mix.map((source) => (
                <li key={source.provider}>
                  <span>{source.provider}</span>
                  <span className="ws-muted">{formatCount(source.articles, "article")}</span>
                  <span className="ws-muted">{formatCount(source.publishers, "publisher")}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="ws-grid-2 ws-grid-wide-left">
        <Panel
          title="Priority queue"
          eyebrow="HIGHEST OPERATIONAL PRIORITY IN THE LAST 24H"
          actions={<button type="button" className="ws-button" onClick={() => onNavigate?.("events")}>All events</button>}
        >
          {(data?.important_events || []).length === 0 ? (
            <Empty title="No prioritised events in this window">
              Priority is computed from severity, confidence, corroboration and event state. With no stored events in
              the last 24 hours this list stays empty rather than showing examples.
            </Empty>
          ) : (
            <div className="ws-event-list">
              {data.important_events.map((event) => (
                <EventRow key={event.id} event={event} onSelect={handleSelect} />
              ))}
            </div>
          )}
        </Panel>

        <div className="ws-stack">
          <Panel title="Coverage" eyebrow="HOW COMPLETE IS THIS PICTURE">
            <dl className="ws-facts">
              <div><dt>Events with coordinates</dt><dd>{formatNumber(data?.coverage?.events_with_coordinates)}</dd></div>
              <div><dt>Country-level only</dt><dd>{formatNumber(data?.coverage?.events_country_only)}</dd></div>
              <div><dt>Unknown location</dt><dd>{formatNumber(data?.coverage?.events_unknown_location)}</dd></div>
              <div><dt>Earliest event</dt><dd>{formatRelativeTime(data?.coverage?.earliest_event_at, "none stored")}</dd></div>
              <div><dt>Last ingestion</dt><dd>{formatRelativeTime(data?.freshness?.latest_ingestion, "no run recorded")}</dd></div>
            </dl>
            <p className="ws-muted ws-small">
              Collection coverage differs by region and language. Absence of events is not evidence of calm.
            </p>
          </Panel>

          <Panel
            title="Anomalies"
            eyebrow="STATISTICAL DEVIATIONS"
            actions={<button type="button" className="ws-button" onClick={() => onNavigate?.("alerts")}>Alert centre</button>}
          >
            {anomalies.error ? (
              <p className="ws-error-text">{anomalies.error?.response?.data?.detail || "Anomaly detection failed."}</p>
            ) : (anomalies.data?.items || []).length === 0 ? (
              <p className="ws-muted ws-small">
                No anomaly cleared the detection threshold (2σ against a 14-day baseline with at least 3 observed and 3
                baseline events). This is a coverage-limited baseline, not a guarantee of normality.
              </p>
            ) : (
              <ul className="ws-anomaly-list">
                {anomalies.data.items.slice(0, 5).map((anomaly) => (
                  <li key={anomaly.id}>
                    <Badge tone="warn">{anomaly.dimension?.replace(/_/g, " ")}</Badge>
                    <strong>{String(anomaly.key || "").replace(/_/g, " ")}</strong>
                    <span className="ws-muted">
                      {formatNumber(anomaly.observed)} observed vs {formatNumber(anomaly.baseline, 1)} baseline
                      {anomaly.deviation ? ` · ${formatNumber(anomaly.deviation, 1)}σ` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <Panel title="Event state" eyebrow="LIFECYCLE">
        {(data?.event_states || []).length === 0 ? (
          <Empty title="No lifecycle data" />
        ) : (
          <div className="ws-chip-row">
            {data.event_states.map((state) => (
              <Badge key={state.state} tone={STATE_TONES[state.state] || "muted"}>
                {String(state.state || "unknown").replace(/_/g, " ")} · {formatNumber(state.count)}
              </Badge>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
