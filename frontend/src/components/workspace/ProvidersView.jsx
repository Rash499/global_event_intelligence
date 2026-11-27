import { useState } from "react";

import { getIngestionStatus, getProviderHistory, getProviders, runProviderIngestion } from "../../services/api.jsx";
import { formatDateTime, formatRelativeTime } from "../../services/dateFormat.jsx";
import { formatNumber, humanise } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, DataTable, Empty, ErrorState, Loading, Panel, SourceNote, Toolbar } from "./primitives.jsx";

/**
 * Provider health and collection runs.
 *
 * Every provider is shown with the integration status the backend actually
 * reported. Credential-gated providers say "needs configuration" instead of
 * pretending to be live, and a provider that has never run is "idle", not
 * "healthy".
 */
const STATUS_TONE = {
  healthy: "ok",
  idle: "muted",
  degraded: "warn",
  unavailable: "danger",
  not_configured: "muted",
  disabled: "muted",
};

const STATUS_COPY = {
  healthy: "Working — last run succeeded",
  idle: "Configured, no run recorded yet",
  degraded: "Working with errors — last run recovered after retries or partial failures",
  unavailable: "Failing — the last attempt errored",
  not_configured: "Needs configuration (credentials or feed URL not set)",
  disabled: "Disabled in configuration",
};

export default function ProvidersView() {
  const providers = useApiResource(() => getProviders(true), [], { pollMs: 60000 });
  const [selected, setSelected] = useState(null);
  const [running, setRunning] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [runError, setRunError] = useState("");
  const history = useApiResource(() => getProviderHistory(selected, 40), [selected], { enabled: Boolean(selected) });

  const [runNotice, setRunNotice] = useState("");

  const waitForRunningIngestion = async () => {
    // A 409 means a run (possibly the scheduler's) is already in progress.
    // That's a normal state, not an error: wait for it, then refresh.
    for (let attempt = 0; attempt < 100; attempt += 1) {
      try {
        const status = await getIngestionStatus();
        if (!status?.running) return;
      } catch {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
  };

  const runOne = async (key) => {
    setRunning(key);
    setRunError("");
    setRunResult(null);
    setRunNotice("");
    try {
      const result = await runProviderIngestion(key);
      setRunResult({ key, result });
      await providers.reload();
    } catch (caught) {
      if (caught?.response?.status === 409) {
        setRunNotice("A collection is already running — waiting for it to finish, then refreshing status.");
        await waitForRunningIngestion();
        await providers.reload();
        setRunNotice("The running collection finished; status refreshed. Use Collect now to run this provider again.");
      } else {
        setRunError(caught?.response?.data?.detail || `Running ${key} failed.`);
      }
    } finally {
      setRunning(null);
    }
  };

  const items = providers.data?.items || [];

  return (
    <div className="ws-view ws-providers">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">DATA SOURCES</p>
          <h1>Provider health</h1>
          <p className="ws-subtitle">
            Status comes from real collection runs. A provider that needs credentials is reported as needing
            configuration — it is never counted as integrated.
          </p>
        </div>
        <div className="ws-head-meta">
          <button type="button" className="ws-button" onClick={providers.reload}>Refresh</button>
        </div>
      </header>

      {providers.data?.by_status && (
        <div className="ws-chip-row">
          {Object.entries(providers.data.by_status).map(([status, count]) => (
            <Badge key={status} tone={STATUS_TONE[status] || "muted"}>
              {humanise(status)} · {count}
            </Badge>
          ))}
        </div>
      )}

      {runError && <p className="ws-error-text" role="alert">{runError}</p>}
      {runNotice && <p className="ws-inline-note" role="status">{runNotice}</p>}
      {runResult && (
        <p className="ws-inline-note">
          <strong>{runResult.key}</strong> finished: {formatNumber(runResult.result?.events_created)} events created,{" "}
          {formatNumber(runResult.result?.articles_seen)} articles seen
          {runResult.result?.errors ? ` · ${runResult.result.errors.length} error(s)` : ""}.
        </p>
      )}

      {providers.error ? (
        <ErrorState error={providers.error} onRetry={providers.reload} />
      ) : providers.loading && !providers.data ? (
        <Loading label="Loading provider status" />
      ) : items.length === 0 ? (
        <Empty title="No providers registered" />
      ) : (
        <div className="ws-provider-grid">
          {items.map((provider) => (
            <article key={provider.provider || provider.key} className={`ws-provider-card tone-${STATUS_TONE[provider.status] || "muted"}`}>
              <header>
                <div>
                  <h2>{provider.name || humanise(provider.provider || provider.key)}</h2>
                  <span className="ws-muted ws-small">{humanise(provider.provider_type || provider.key || provider.provider)}</span>
                </div>
                <Badge tone={STATUS_TONE[provider.status] || "muted"}>{humanise(provider.status)}</Badge>
              </header>

              <p className="ws-muted ws-small">{STATUS_COPY[provider.status] || "Status not reported"}</p>

              <dl className="ws-facts ws-facts-compact">
                <div><dt>Enabled</dt><dd>{provider.enabled ? "yes" : "no"}</dd></div>
                <div><dt>Last success</dt><dd>{formatRelativeTime(provider.last_success_at, "never")}</dd></div>
                <div><dt>Last attempt</dt><dd>{formatRelativeTime(provider.last_attempt_at, "never")}</dd></div>
                <div><dt>Consecutive failures</dt><dd>{formatNumber(provider.consecutive_failures ?? 0)}</dd></div>
                {provider.last_error && <div><dt>Last error</dt><dd className="ws-error-text">{provider.last_error}</dd></div>}
                {provider.requires_credentials && <div><dt>Requires</dt><dd>credentials</dd></div>}
                {provider.verification_status === "unverified" && <div><dt>Verification</dt><dd>Unverified — never run against a real account; live operation not claimed</dd></div>}
              </dl>

              <div className="ws-provider-actions">
                <button
                  type="button"
                  className="ws-button"
                  onClick={() => runOne(provider.provider || provider.key)}
                  disabled={running !== null || !provider.enabled}
                  title={!provider.enabled ? "Provider is disabled in configuration" : running !== null ? "A collection is already running" : undefined}
                >
                  {running === (provider.provider || provider.key) ? "Collecting…" : "Collect now"}
                </button>
                <button type="button" className="ws-button ws-button-quiet" onClick={() => setSelected((provider.provider || provider.key) === selected ? null : provider.provider || provider.key)}>
                  {selected === (provider.provider || provider.key) ? "Hide runs" : "Run history"}
                </button>
              </div>

              {selected === (provider.provider || provider.key) && (
                <div className="ws-provider-history">
                  {history.error ? (
                    <p className="ws-error-text">{history.error?.response?.data?.detail || "History unavailable."}</p>
                  ) : history.loading && !history.data ? (
                    <Loading label="Loading runs" />
                  ) : (
                    <DataTable
                      empty="No runs recorded for this provider"
                      rows={history.data?.items || []}
                      rowKey={(row) => row.id}
                      columns={[
                        { key: "started_at", label: "Started", render: (row) => (row.started_at ? formatDateTime(row.started_at) : "—") },
                        { key: "status", label: "Status", render: (row) => <Badge tone={STATUS_TONE[row.status] || "muted"}>{row.status}</Badge> },
                        { key: "records_received", label: "Records", align: "right", render: (row) => formatNumber(row.records_received) },
                        { key: "records_failed", label: "Failed", align: "right", render: (row) => formatNumber(row.records_failed) },
                        { key: "events_created", label: "Events", align: "right", render: (row) => formatNumber(row.events_created) },
                        { key: "duration_ms", label: "Duration", align: "right", render: (row) => (row.duration_ms != null ? `${formatNumber(row.duration_ms)} ms` : "—") },
                      ]}
                    />
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <Panel title="How to add a source" eyebrow="OPERATIONS">
        <ol className="ws-bullets">
          <li>RSS, GDELT, Google News, USGS and WHO are keyless and work with the shipped defaults. ReliefWeb (API v2) additionally needs a pre-approved appname.</li>
          <li>NASA FIRMS requires a free MAP_KEY; CAP requires feed URLs; ACLED requires a licensed account, is marked unverified (never run against a real account), and is never enabled by default.</li>
          <li>Set the credential in <code>backend/.env</code>, restart the API, then confirm the provider flips from “needs configuration” to “idle”, then “healthy” after the first successful run.</li>
          <li>A provider is only reported as integrated when its health endpoint says so — the docs list the same status.</li>
        </ol>
        <SourceNote>
          One failing provider never blocks the others: the runner isolates each provider, records the failure, and the
          scheduler continues.
        </SourceNote>
      </Panel>
    </div>
  );
}
