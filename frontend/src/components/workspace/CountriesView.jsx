import { useCallback, useState } from "react";

import { getCountriesSummary, getCountryRisk } from "../../services/api.jsx";
import { formatCount, formatNumber, severityColour } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, DataTable, Empty, ErrorState, Explain, Loading, Meter, Panel, SourceNote, Stat } from "./primitives.jsx";

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
 * The backend deliberately does not return one "risk score". It returns
 * per-dimension counts and severity averages plus a coverage caveat, because a
 * country with no collected reporting would otherwise look safe. The UI keeps
 * that structure instead of collapsing it.
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
            Descriptive statistics over collected reporting, grouped by taxonomy category. Not a forecast, and not a
            composite risk index.
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
                </div>
                <p className={`ws-coverage-note tone-${COVERAGE_TONE[coverage?.level] || "muted"}`}>
                  <strong>Coverage: {coverage?.level || "unknown"}.</strong> {coverage?.note}
                </p>
              </Panel>

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
                        <Meter
                          value={dimension.average_severity || 0}
                          max={10}
                          colour={severityColour(dimension.average_severity)}
                          label={`${DIMENSION_LABELS[dimension.dimension] || dimension.dimension} mean severity`}
                          caption={`mean ${formatNumber(dimension.average_severity, 2)} · max ${formatNumber(dimension.max_severity, 1)} · ${formatCount(dimension.developing_events, "developing")}`}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              </Panel>

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
