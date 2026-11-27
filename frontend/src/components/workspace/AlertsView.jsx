import { useState } from "react";

import {
  createAlertRule,
  deleteAlertRule,
  dismissAnomaly,
  getAlertRules,
  getAlerts,
  getAnomalies,
  updateAlertStatus,
} from "../../services/api.jsx";
import { formatDateTime } from "../../services/dateFormat.jsx";
import { formatNumber, severityColour } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, Empty, ErrorState, Explain, Loading, Panel, SourceNote, Toolbar } from "./primitives.jsx";

const STATUSES = ["new", "acknowledged", "resolved", "dismissed"];

const blankRule = {
  name: "",
  country_code: "",
  category: "",
  min_severity: "",
  min_confidence: "",
  keywords: "",
};

export default function AlertsView({ onSelectEvent }) {
  const [status, setStatus] = useState("new");
  const alerts = useApiResource(() => getAlerts(status), [status]);
  const rules = useApiResource(() => getAlertRules(), []);
  const anomalies = useApiResource(() => getAnomalies(), []);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState(blankRule);

  const mutateAlert = async (id, next) => {
    setBusy(id);
    setError("");
    try {
      await updateAlertStatus(id, next);
      await alerts.reload();
    } catch (caught) {
      setError(caught?.response?.data?.detail || "Updating the alert failed.");
    } finally {
      setBusy(null);
    }
  };

  const removeRule = async (id) => {
    setBusy(`rule-${id}`);
    try {
      await deleteAlertRule(id);
      await rules.reload();
    } catch (caught) {
      setError(caught?.response?.data?.detail || "Deleting the rule failed.");
    } finally {
      setBusy(null);
    }
  };

  const addRule = async () => {
    if (draft.name.trim().length < 2) {
      setError("A rule needs a name of at least 2 characters.");
      return;
    }
    setBusy("rule-new");
    setError("");
    try {
      await createAlertRule({
        name: draft.name.trim(),
        country_code: draft.country_code ? draft.country_code.toUpperCase() : undefined,
        category: draft.category || undefined,
        min_severity: draft.min_severity === "" ? undefined : Number(draft.min_severity),
        min_confidence: draft.min_confidence === "" ? undefined : Number(draft.min_confidence),
        keywords: draft.keywords || undefined,
      });
      setDraft(blankRule);
      await rules.reload();
    } catch (caught) {
      setError(caught?.response?.data?.detail || "Creating the rule failed.");
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async (id) => {
    setBusy(`anomaly-${id}`);
    try {
      await dismissAnomaly(id);
      await anomalies.reload();
    } catch (caught) {
      setError(caught?.response?.data?.detail || "Dismissing the anomaly failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="ws-view ws-alerts">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">ALERT CENTRE</p>
          <h1>Alerts & anomalies</h1>
          <p className="ws-subtitle">
            Rules evaluate stored events during collection. Anomalies compare the last period against a trailing
            baseline — both are signals to review, not confirmed incidents.
          </p>
        </div>
      </header>

      {error && <p className="ws-error-text" role="alert">{error}</p>}

      <div className="ws-grid-main-aside">
        <Panel
          title="Triggered alerts"
          eyebrow={alerts.data?.by_status ? Object.entries(alerts.data.by_status).map(([key, value]) => `${value} ${key}`).join(" · ") : undefined}
          actions={
            <div className="ws-segmented ws-segmented-small" role="group" aria-label="Filter alerts by status">
              {STATUSES.map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={status === option}
                  className={status === option ? "is-active" : ""}
                  onClick={() => setStatus(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          }
        >
          {alerts.error ? (
            <ErrorState error={alerts.error} onRetry={alerts.reload} />
          ) : alerts.loading && !alerts.data ? (
            <Loading label="Loading alerts" />
          ) : (alerts.data?.items || []).length === 0 ? (
            <Empty title={`No ${status} alerts`}>
              Alerts appear when a stored event matches an enabled rule. Create a rule below, or check another status
              filter.
            </Empty>
          ) : (
            <ul className="ws-alert-list">
              {alerts.data.items.map((alert) => (
                <li key={alert.id} className={`tone-${alert.status}`}>
                  <div className="ws-alert-head">
                    <Badge tone={alert.status === "new" ? "danger" : "muted"}>{alert.status}</Badge>
                    <button
                      type="button"
                      className="ws-link"
                      onClick={() => alert.event_id && onSelectEvent?.({ id: alert.event_id })}
                    >
                      {alert.event_title || alert.title || `Alert #${alert.id}`}
                    </button>
                    {alert.event_severity != null && (
                      <Badge colour={severityColour(alert.event_severity)}>
                        severity {formatNumber(alert.event_severity, 1)}
                      </Badge>
                    )}
                  </div>
                  <div className="ws-alert-meta">
                    {alert.rule_name && <span>rule: {alert.rule_name}</span>}
                    {alert.country_code && <span>{alert.country_code}</span>}
                    <span>{alert.triggered_at ? formatDateTime(alert.triggered_at) : "time unknown"}</span>
                  </div>
                  {alert.evidence && (
                    <Explain summary="Rule evidence">
                      <pre className="ws-pre">{JSON.stringify(alert.evidence, null, 2)}</pre>
                    </Explain>
                  )}
                  <div className="ws-alert-actions">
                    {alert.status !== "acknowledged" && (
                      <button type="button" className="ws-button" disabled={busy === alert.id} onClick={() => mutateAlert(alert.id, "acknowledged")}>
                        Acknowledge
                      </button>
                    )}
                    {alert.status !== "resolved" && (
                      <button type="button" className="ws-button" disabled={busy === alert.id} onClick={() => mutateAlert(alert.id, "resolved")}>
                        Resolve
                      </button>
                    )}
                    {alert.status !== "dismissed" && (
                      <button type="button" className="ws-button ws-button-quiet" disabled={busy === alert.id} onClick={() => mutateAlert(alert.id, "dismissed")}>
                        Dismiss
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="ws-stack">
          <Panel title="Detection rules" eyebrow="WHAT RAISES AN ALERT">
            {rules.error ? (
              <ErrorState error={rules.error} onRetry={rules.reload} />
            ) : (rules.data?.items || []).length === 0 ? (
              <p className="ws-muted ws-small">No rules configured. Without rules, no alerts will be raised.</p>
            ) : (
              <ul className="ws-rule-list">
                {rules.data.items.map((rule) => (
                  <li key={rule.id}>
                    <div>
                      <strong>{rule.name}</strong>
                      <div className="ws-muted ws-small">
                        {[
                          rule.country_code && `country ${rule.country_code}`,
                          rule.category && `category ${rule.category}`,
                          rule.min_severity != null && `severity ≥ ${rule.min_severity}`,
                          rule.min_confidence != null && `confidence ≥ ${rule.min_confidence}`,
                          rule.keywords && `keywords “${rule.keywords}”`,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "no conditions — matches everything"}
                      </div>
                    </div>
                    <button type="button" className="ws-icon-button" onClick={() => removeRule(rule.id)} disabled={busy === `rule-${rule.id}`} aria-label={`Delete ${rule.name}`}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="ws-form-grid">
              <label className="ws-field">
                <span>Name</span>
                <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Severe events in Japan" />
              </label>
              <label className="ws-field ws-field-narrow">
                <span>Country</span>
                <input maxLength={2} value={draft.country_code} onChange={(event) => setDraft({ ...draft, country_code: event.target.value.toUpperCase() })} placeholder="JP" />
              </label>
              <label className="ws-field">
                <span>Category</span>
                <input value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} placeholder="natural_disaster" />
              </label>
              <label className="ws-field ws-field-narrow">
                <span>Min severity</span>
                <input type="number" min="0" max="10" step="0.5" value={draft.min_severity} onChange={(event) => setDraft({ ...draft, min_severity: event.target.value })} />
              </label>
              <label className="ws-field ws-field-narrow">
                <span>Min confidence</span>
                <input type="number" min="0" max="1" step="0.05" value={draft.min_confidence} onChange={(event) => setDraft({ ...draft, min_confidence: event.target.value })} />
              </label>
              <label className="ws-field">
                <span>Keywords</span>
                <input value={draft.keywords} onChange={(event) => setDraft({ ...draft, keywords: event.target.value })} placeholder="evacuation, tsunami" />
              </label>
              <button type="button" className="ws-button" onClick={addRule} disabled={busy === "rule-new"}>
                Add rule
              </button>
            </div>
          </Panel>

          <Panel title="Anomalies" eyebrow="DEVIATIONS FROM BASELINE">
            {anomalies.error ? (
              <ErrorState error={anomalies.error} onRetry={anomalies.reload} />
            ) : (anomalies.data?.items || []).length === 0 ? (
              <p className="ws-muted ws-small">
                No anomaly currently exceeds the detection threshold. Detection needs at least 3 observed and 3
                baseline events per dimension, so a sparse database cannot produce anomalies — that is a coverage
                limit, not a quiet world.
              </p>
            ) : (
              <ul className="ws-anomaly-list">
                {anomalies.data.items.map((anomaly) => (
                  <li key={anomaly.id}>
                    <div className="ws-alert-head">
                      <Badge tone="warn">{String(anomaly.dimension || "").replace(/_/g, " ")}</Badge>
                      <strong>{String(anomaly.key || "").replace(/_/g, " ")}</strong>
                      <span className="ws-muted">
                        {formatNumber(anomaly.observed)} vs {formatNumber(anomaly.baseline, 1)} baseline
                        {anomaly.deviation ? ` · ${formatNumber(anomaly.deviation, 1)}σ` : ""}
                      </span>
                      <button type="button" className="ws-icon-button" onClick={() => dismiss(anomaly.id)} disabled={busy === `anomaly-${anomaly.id}`} aria-label="Dismiss anomaly">
                        ×
                      </button>
                    </div>
                    {anomaly.explanation && <p className="ws-muted ws-small">{anomaly.explanation}</p>}
                    {Array.isArray(anomaly.limitations) && anomaly.limitations.length > 0 && (
                      <Explain summary="Limitations">
                        <ul className="ws-bullets">
                          {anomaly.limitations.map((limitation) => (
                            <li key={limitation}>{limitation}</li>
                          ))}
                        </ul>
                      </Explain>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <SourceNote>
              Detected: {formatNumber(anomalies.data?.newly_detected ?? 0)} new in the latest evaluation,{" "}
              {formatNumber(anomalies.data?.count ?? 0)} stored.
            </SourceNote>
          </Panel>
        </div>
      </div>
    </div>
  );
}
