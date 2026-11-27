import { useState } from "react";

import { generateReport, listReports, reportExportUrl } from "../../services/api.jsx";
import { formatDateTime } from "../../services/dateFormat.jsx";
import { formatNumber } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, DataTable, Empty, ErrorState, Explain, Loading, Panel, SourceNote } from "./primitives.jsx";

const SCOPES = [
  { id: "global", label: "Global" },
  { id: "country", label: "Country" },
  { id: "category", label: "Category" },
  { id: "event", label: "Single event" },
];

/**
 * Reports are assembled from stored records and cite what they were built from.
 * Export downloads the server-rendered CSV/HTML rather than a client-side
 * reconstruction, so the file matches the stored report exactly.
 */
export default function ReportsView({ onSelectEvent }) {
  const reports = useApiResource(() => listReports(), []);
  const [scope, setScope] = useState("global");
  const [scopeValue, setScopeValue] = useState("");
  const [days, setDays] = useState(7);
  const [includeAi, setIncludeAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [current, setCurrent] = useState(null);

  const build = async () => {
    setBusy(true);
    setError("");
    try {
      const report = await generateReport({
        scope,
        scope_value: scopeValue || undefined,
        days: Number(days) || 7,
        include_ai: includeAi,
      });
      setCurrent(report);
      await reports.reload();
    } catch (caught) {
      setError(caught?.response?.data?.detail || "Report generation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ws-view ws-reports">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">DELIVERABLES</p>
          <h1>Reports</h1>
          <p className="ws-subtitle">
            Every report states its scope, period, the events it cites and the coverage limits of the data behind it.
            AI narrative is optional and labelled when used.
          </p>
        </div>
      </header>

      <div className="ws-grid-main-aside">
        <div className="ws-stack">
          <Panel title="Generate" eyebrow="SCOPE & PERIOD">
            <div className="ws-form-grid">
              <label className="ws-field">
                <span>Scope</span>
                <select value={scope} onChange={(event) => setScope(event.target.value)}>
                  {SCOPES.map((option) => (
                    <option key={option.id} value={option.id}>{option.label}</option>
                  ))}
                </select>
              </label>
              {scope !== "global" && (
                <label className="ws-field">
                  <span>{scope === "country" ? "Country code" : scope === "category" ? "Category key" : "Event id"}</span>
                  <input
                    value={scopeValue}
                    onChange={(event) => setScopeValue(event.target.value)}
                    placeholder={scope === "country" ? "JP" : scope === "category" ? "natural_disaster" : "1234"}
                  />
                </label>
              )}
              <label className="ws-field ws-field-narrow">
                <span>Days</span>
                <input type="number" min="1" max="365" value={days} onChange={(event) => setDays(event.target.value)} />
              </label>
              <label className="ws-checkbox">
                <input type="checkbox" checked={includeAi} onChange={(event) => setIncludeAi(event.target.checked)} />
                Include AI assessment (labelled, not verified fact)
              </label>
              <button type="button" className="ws-button" onClick={build} disabled={busy}>
                {busy ? "Building…" : "Generate report"}
              </button>
            </div>
            {error && <p className="ws-error-text" role="alert">{error}</p>}
          </Panel>

          {current && (
            <Panel
              title={current.title || "Report"}
              eyebrow={`${String(current.scope || "").toUpperCase()} · ${formatDateTime(current.generated_at)}`}
              actions={
                <div className="ws-chip-row">
                  <a className="ws-button" href={reportExportUrl(current.id, "csv")} download>CSV</a>
                  <a className="ws-button" href={reportExportUrl(current.id, "html")} target="_blank" rel="noopener noreferrer">HTML</a>
                </div>
              }
            >
              {(current.sections || []).map((section, index) => (
                <section key={`${section.title}-${index}`} className="ws-report-section">
                  <h3>{section.title}</h3>
                  {section.body && <p className="ws-body-text">{section.body}</p>}
                  {Array.isArray(section.items) && section.items.length > 0 && (
                    <ul className="ws-bullets">
                      {section.items.map((item, i) => (
                        <li key={i}>{typeof item === "string" ? item : item.title || JSON.stringify(item)}</li>
                      ))}
                    </ul>
                  )}
                  {Array.isArray(section.events) && section.events.length > 0 && (
                    <ul className="ws-compact-list">
                      {section.events.map((event) => (
                        <li key={event.id}>
                          <button type="button" className="ws-link" onClick={() => onSelectEvent?.({ id: event.id, event })}>
                            {event.title}
                          </button>
                          <span className="ws-muted">
                            {event.severity != null ? `severity ${formatNumber(event.severity, 1)}` : "not assessed"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
              {current.ai_narrative && (
                <div className="ws-ai-note">
                  <strong>AI-generated assessment — not verified fact</strong>
                  <p>{current.ai_narrative}</p>
                </div>
              )}
              {current.limitations && (
                <Explain summary="Coverage & limitations">
                  <ul className="ws-bullets">
                    {(Array.isArray(current.limitations) ? current.limitations : [current.limitations]).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </Explain>
              )}
            </Panel>
          )}
        </div>

        <Panel title="Stored reports" eyebrow="HISTORY">
          {reports.error ? (
            <ErrorState error={reports.error} onRetry={reports.reload} />
          ) : reports.loading && !reports.data ? (
            <Loading label="Loading reports" />
          ) : (reports.data?.items || []).length === 0 ? (
            <Empty title="No reports yet">Generate one above; it will be stored and exportable.</Empty>
          ) : (
            <DataTable
              rows={reports.data.items}
              rowKey={(row) => row.id}
              columns={[
                { key: "title", label: "Title", render: (row) => <span>{row.title}</span> },
                { key: "scope", label: "Scope", render: (row) => <Badge>{row.scope}{row.scope_value ? `: ${row.scope_value}` : ""}</Badge> },
                { key: "generated_at", label: "Generated", render: (row) => (row.generated_at ? formatDateTime(row.generated_at) : "—") },
                {
                  key: "export",
                  label: "Export",
                  render: (row) => (
                    <span className="ws-chip-row">
                      <a className="ws-link" href={reportExportUrl(row.id, "csv")} download>CSV</a>
                      <a className="ws-link" href={reportExportUrl(row.id, "html")} target="_blank" rel="noopener noreferrer">HTML</a>
                    </span>
                  ),
                },
              ]}
            />
          )}
          <SourceNote>
            PDF export is not implemented yet; HTML prints cleanly to PDF from the browser. This is stated here rather
            than offered as a button that would silently fall back to something else.
          </SourceNote>
        </Panel>
      </div>
    </div>
  );
}
