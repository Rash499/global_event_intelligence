import { useCallback, useState } from "react";

import { getCountriesSummary, getCountryRisk } from "../../services/api.jsx";
import { formatCount, formatNumber, severityColour } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { MAP_LAYERS } from "../globe/mapLayers.jsx";
import { Badge, DataTable, Empty, ErrorState, Explain, Loading, Meter, Panel, SourceNote, Stat } from "./primitives.jsx";

const TREND_ARROWS = { rising: "▲", falling: "▼", steady: "→" };

/** 7-day lanes × days activity grid, grouped by the map layer registry. */
function LaneTimeline({ timeline }) {
  const days = timeline?.days || [];
  if (!days.length) return null;
  return (
    <div className="ws-lane-timeline">
      <div className="ws-lane-row ws-lane-head" aria-hidden="true">
        <span />
        {days.map((day) => (
          <span key={day.date} title={day.date}>{day.date.slice(5)}</span>
        ))}
      </div>
      {MAP_LAYERS.map((layer) => (
        <div className="ws-lane-row" key={layer.id}>
          <span className="ws-lane-label">{layer.glyph} {layer.label}</span>
          {days.map((day) => {
            let events = 0;
            let maxSeverity = null;
            for (const category of layer.categories) {
              const cell = day.by_category?.[category];
              if (!cell) continue;
              events += cell.events || 0;
              if (cell.max_severity != null) {
                maxSeverity = maxSeverity == null ? cell.max_severity : Math.max(maxSeverity, cell.max_severity);
              }
            }
            return (
              <span
                key={day.date}
                className="ws-lane-cell"
                style={events ? { background: `${severityColour(maxSeverity)}38`, color: "var(--text)" } : undefined}
                title={
                  events
                    ? `${layer.label} · ${day.date}: ${events} stored event${events === 1 ? "" : "s"}, max severity ${maxSeverity == null ? "not assessed" : formatNumber(maxSeverity, 1)}`
                    : `${layer.label} · ${day.date}: nothing collected`
                }
              >
                {events || "·"}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const DIMENSION_LABELS = {
  conflict_security: "Conflict & security",
  political_instability: "Political instability",
  civil_unrest: "Civil unrest",
  natural_disasters: "Natural disasters",
  public_health: "Public health",
  humanitarian: "Humanitarian",
  economic: "Economic",
  energy_infrastructure: "Energy & infrastructure",
  environment: "Environment",
};

const COVERAGE_TONE = { none: "danger", sparse: "warn", partial: "warn", good: "ok" };

/**
 * Country intelligence.
 *
 * The backend returns a transparent composite indicator alongside its source
 * dimensions and coverage caveat; the score is descriptive, not predictive.
 */
export default function CountriesView({ initialSelection, onSelectEvent }) {
  const [selected, setSelected] = useState(initialSelection?.country ? initialSelection.country : initialSelection || null);
  const [days, setDays] = useState(30);

  const summary = useApiResource(() => getCountriesSummary(days), [days]);
  const risk = useApiResource(
    () => getCountryRisk(selected, days),
    [selected, days],
    { enabled: Boolean(selected) }
  );

  const pick = useCallback((code) => setSelected(code), []);

  const coverage = risk.data?.coverage;

  return (
    <div className="ws-view ws-countries">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">COUNTRY INTELLIGENCE</p>
          <h1>Country indicators</h1>
          <p className="ws-subtitle">
            A transparent country-instability indicator over collected reporting, with source coverage shown alongside it. Descriptive only; not a forecast.
          </p>
        </div>
        <div className="ws-head-meta">
          <label className="ws-field ws-field-narrow">
            <span>Period (days)</span>
            <input
              type="number" min="1" max="365" value={days}
              onChange={(event) => setDays(Math.max(1, Math.min(365, Number(event.target.value) || 30)))}
            />
          </label>
        </div>
      </header>

      <div className="ws-grid-main-aside">
        <Panel title="Countries" eyebrow={`${formatCount(summary.data?.count ?? 0, "country", "countries")} WITH STORED EVENTS`}>
          {summary.error ? (
            <ErrorState error={summary.error} onRetry={summary.reload} />
          ) : summary.loading && !summary.data ? (
            <Loading label="Loading countries" />
          ) : (
            <DataTable
              caption="Click a country to open its indicator breakdown"
              empty="No country attributed events in this period"
              rows={summary.data?.items || []}
              rowKey={(row) => row.country_code}
              onRowClick={(row) => pick(row.country_code)}
              columns={[
                {
                  key: "country",
                  label: "Country",
                  render: (row) => (
                    <button type="button" className="ws-link" onClick={() => pick(row.country_code)}>
                      {row.country || row.country_code} <span className="ws-muted">{row.country_code}</span>
                    </button>
                  ),
                },
                { key: "event_count", label: "Events", align: "right", render: (row) => formatNumber(row.event_count) },
                {
                  key: "max_severity",
                  label: "Max severity",
                  align: "right",
                  render: (row) =>
                    row.max_severity == null ? (
                      "—"
                    ) : (
                      <Badge colour={severityColour(row.max_severity)}>{formatNumber(row.max_severity, 1)}</Badge>
                    ),
                },
                {
                  key: "average_severity",
                  label: "Mean severity",
                  align: "right",
                  render: (row) => (row.average_severity == null ? "—" : formatNumber(row.average_severity, 2)),
                },
                { key: "developing", label: "Developing", align: "right", render: (row) => formatNumber(row.developing) },
                {
                  key: "trend",
                  label: "7d trend",
                  align: "right",
                  render: (row) =>
                    row.trend ? (
                      <span title={`Last 24h: ${row.trend.events_24h} · last 7d: ${row.trend.events_7d} vs previous 7d: ${row.trend.events_previous_7d} (stored reporting volume)`}>
                        {TREND_ARROWS[row.trend.direction] || "→"} {formatNumber(row.trend.events_7d)}
                        <span className="ws-muted"> / {formatNumber(row.trend.events_previous_7d)}</span>
                      </span>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          )}
        </Panel>

        <div className="ws-stack">
          {!selected ? (
            <Empty title="Select a country">Pick a country from the table to see its indicator breakdown.</Empty>
          ) : risk.error ? (
            <ErrorState error={risk.error} onRetry={risk.reload} title="Country indicators unavailable" />
          ) : risk.loading && !risk.data ? (
            <Loading label="Loading country indicators" />
          ) : (
            <>
              <Panel title={risk.data.country} eyebrow={`${risk.data.country_code} · LAST ${risk.data.period_days} DAYS`}>
                <div className="ws-stat-grid ws-stat-grid-compact">
                  <Stat label="Events" value={risk.data.total_events} />
                  <Stat label="Articles" value={risk.data.articles} />
                  <Stat label="Publishers" value={risk.data.publishers} />
                  <Stat label="Events · 24h" value={risk.data.movement?.events_24h} />
                  <Stat label="Events · 7d" value={risk.data.movement?.events_7d} />
                </div>
                {risk.data.movement && (
                  <p className="ws-muted ws-small">
                    Movement compares stored reporting volume: previous 24h{" "}
                    {formatNumber(risk.data.movement.events_previous_24h)} events, previous 7d{" "}
                    {formatNumber(risk.data.movement.events_previous_7d)} events. A rise or fall can
                    reflect collection volume as much as conditions on the ground.
                  </p>
                )}
                <p className={`ws-coverage-note tone-${COVERAGE_TONE[coverage?.level] || "muted"}`}>
                  <strong>Coverage: {coverage?.level || "unknown"}.</strong> {coverage?.note}
                </p>
              </Panel>

              {risk.data.risk_score && (
                <Panel title="Instability score" eyebrow={risk.data.risk_score.level?.toUpperCase()}>
                  <div className="ws-stat-grid ws-stat-grid-compact">
                    <Stat label="Combined score" value={`${formatNumber(risk.data.risk_score.score, 1)}/100`} hint={risk.data.risk_score.formula} />
                    <Stat label="Static baseline" value={risk.data.risk_score.baseline?.score} hint={risk.data.risk_score.baseline?.source} />
                    <Stat label="Event score" value={risk.data.risk_score.event_score} />
                  </div>
                  <p className="ws-muted ws-small">Components: unrest {formatNumber(risk.data.risk_score.components?.unrest, 1)}, conflict {formatNumber(risk.data.risk_score.components?.conflict, 1)}, security {formatNumber(risk.data.risk_score.components?.security, 1)}, information {formatNumber(risk.data.risk_score.components?.information, 1)}.</p>
                  <p className="ws-muted ws-small">Provider boosts: {Object.entries(risk.data.risk_score.boosts || {}).map(([name, item]) => `${name.replace(/_/g, " ")} +${formatNumber(item.score, 1)}/${item.cap}`).join(" · ")}. Floors applied: {(risk.data.risk_score.floors_applied || []).join(", ") || "none in this period (no ingested Level 3/4 advisory or UCDP conflict history)"}.</p>
                  {risk.data.risk_score.coverage?.warning && <p className="ws-coverage-note tone-warn"><strong>Coverage warning.</strong> {risk.data.risk_score.coverage.warning}</p>}
                  <Explain summary="Formula and limitations">
                    <p className="ws-muted ws-small">Baseline weight 40%; event score weight 60%. Event components use unrest 25%, conflict 30%, security 20%, and information 25%. Provider boosts are individually capped; the result is clamped to 0–100. No predictive claim is implied.</p>
                  </Explain>
                </Panel>
              )}

              {(risk.data.active_signals || []).length > 0 && (
                <Panel title="Active signals" eyebrow="REPORTING CATEGORIES PRESENT">
                  <ul className="ws-chip-row ws-signal-chips">
                    {risk.data.active_signals.map((signal) => (
                      <li key={signal.category} className="ws-signal-chip">
                        <i style={{ background: severityColour(signal.max_severity) }} aria-hidden="true" />
                        {signal.label} · {formatCount(signal.event_count, "event")} · max{" "}
                        {signal.max_severity == null ? "not assessed" : formatNumber(signal.max_severity, 1)}
                      </li>
                    ))}
                  </ul>
                  <SourceNote>
                    A signal means reporting in that category was collected in this period. A missing
                    signal means nothing was collected — not that the category is quiet.
                  </SourceNote>
                </Panel>
              )}

              <Panel title="Indicators" eyebrow="BY DIMENSION">
                <ul className="ws-dimension-list">
                  {(risk.data.dimensions || []).map((dimension) => (
                    <li key={dimension.dimension}>
                      <div className="ws-dimension-head">
                        <strong>{DIMENSION_LABELS[dimension.dimension] || dimension.dimension}</strong>
                        <span className="ws-muted">{formatCount(dimension.event_count, "event")}</span>
                      </div>
                      {dimension.event_count === 0 ? (
                        <p className="ws-muted ws-small">No events in this dimension — reporting gap or genuine quiet, not distinguishable from the data alone.</p>
                      ) : (
                        <>
                        <div
                          className="ws-dimension-countbar"
                          role="img"
                          aria-label={`${formatCount(dimension.event_count, "event")} of ${formatCount(risk.data.total_events, "event")} in this period`}
                          title="Share of this country's stored events in the period"
                        >
                          <span
                            style={{
                              width: `${Math.max(3, Math.round((dimension.event_count / Math.max(1, risk.data.total_events)) * 100))}%`,
                            }}
                          />
                        </div>
                        <Meter
                          value={dimension.average_severity || 0}
                          max={10}
                          colour={severityColour(dimension.average_severity)}
                          label={`${DIMENSION_LABELS[dimension.dimension] || dimension.dimension} mean severity`}
                          caption={`mean ${formatNumber(dimension.average_severity, 2)} · max ${formatNumber(dimension.max_severity, 1)} · ${formatCount(dimension.developing_events, "developing")}`}
                        />
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </Panel>

              {risk.data.timeline && (
                <Panel title="7-day activity" eyebrow="STORED EVENTS BY LAYER AND DAY">
                  <LaneTimeline timeline={risk.data.timeline} />
                  <SourceNote>
                    Each cell counts stored events in that map layer on that day (hover for the worst
                    severity). Empty cells mean nothing was collected that day.
                  </SourceNote>
                </Panel>
              )}

              <Panel title="Recent events" eyebrow="INPUT EVIDENCE">
                {(risk.data.recent_events || []).length === 0 ? (
                  <Empty title="No recent events" />
                ) : (
                  <ul className="ws-compact-list">
                    {risk.data.recent_events.map((event) => (
                      <li key={event.id}>
                        <button type="button" className="ws-link" onClick={() => onSelectEvent?.({ id: event.id, event })}>
                          {event.title}
                        </button>
                        <span className="ws-muted">
                          {event.severity != null ? `severity ${formatNumber(event.severity, 1)}` : "not assessed"}
                          {event.event_state ? ` · ${event.event_state.replace(/_/g, " ")}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title="Method & limitations" eyebrow="READ THIS BEFORE COMPARING">
                <p className="ws-body-text">{risk.data.methodology}</p>
                <Explain summary="Limitations stated by the API">
                  <ul className="ws-bullets">
                    {(risk.data.limitations || []).map((limitation) => (
                      <li key={limitation}>{limitation}</li>
                    ))}
                  </ul>
                </Explain>
                <SourceNote tone="warn">
                  Comparing two countries with different coverage levels compares two collection systems as much as two
                  situations. Read the coverage block first.
                </SourceNote>
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
