import { getIngestionStatus, getSystemStatus, getIntelligenceGaps } from "../../services/api.jsx";
import { formatDateTime } from "../../services/dateFormat.jsx";
import { formatNumber, humanise } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, Empty, ErrorState, Loading, Panel, SourceNote, Stat } from "./primitives.jsx";

/**
 * System status.
 *
 * Read-only and factual: schema migration state, database integrity, scheduler
 * jobs, AI availability and the security posture flags the backend exposes. No
 * secrets are echoed — the API does not send them.
 */
export default function SystemView() {
  const status = useApiResource(() => getSystemStatus(), [], { pollMs: 60000 });
  const ingestion = useApiResource(() => getIngestionStatus(), [], { pollMs: 30000 });
  const gaps = useApiResource(() => getIntelligenceGaps(), [], { pollMs: 60000 });

  if (status.loading && !status.data) return <Loading label="Loading system status" />;
  if (status.error) return <ErrorState error={status.error} onRetry={status.reload} title="System status unavailable" />;

  const data = status.data;
  const db = data?.database || {};
  const migrations = db.migrations || {};
  const scheduler = data?.scheduler || {};

  return (
    <div className="ws-view ws-system">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">OPERATIONS</p>
          <h1>System status</h1>
          <p className="ws-subtitle">
            Runtime facts from the backend: database integrity, migration state, scheduler and AI availability.
          </p>
        </div>
        <div className="ws-head-meta">
          <Badge tone={data?.environment === "production" ? "warn" : "ok"}>{humanise(data?.environment || "unknown")}</Badge>
          <span className="ws-muted">v{data?.version || "—"}</span>
          <button type="button" className="ws-button" onClick={status.reload}>Refresh</button>
        </div>
      </header>

      <div className="ws-stat-grid">
        <Stat label="Database" value={db.available ? "available" : "unavailable"} tone={db.available ? "ok" : "danger"} hint={db.integrity || undefined} />
        <Stat label="Schema version" value={migrations.current_version ?? null} hint={`latest ${migrations.latest_version ?? "?"}${migrations.up_to_date === false ? " · migrations pending" : " · up to date"}`} />
        <Stat label="Database size" value={db.size_bytes ? `${formatNumber(Math.round(db.size_bytes / 1024))} KB` : null} />
        <Stat label="Retention" value={data?.retention_days ? `${data.retention_days} days` : null} hint="historical data window" />
      </div>

      <div className="ws-grid-2">
        <Panel title="Database & migrations" eyebrow="STORAGE">
          <dl className="ws-facts">
            <div><dt>Integrity check</dt><dd>{db.integrity || "not run"}</dd></div>
            <div><dt>Path</dt><dd>{db.path || "unknown"}</dd></div>
            {Array.isArray(migrations.applied) && (
              <div><dt>Applied</dt><dd>{migrations.applied.map((version) => `v${version}`).join(", ") || "none"}</dd></div>
            )}
            <div><dt>Schema current</dt><dd>{migrations.up_to_date ? "yes" : "no — migrations pending"}</dd></div>
            {db.error && <div><dt>Error</dt><dd className="ws-error-text">{db.error}</dd></div>}
          </dl>
          {migrations.up_to_date === false && (
            <SourceNote tone="warn">Migrations are pending. Restart the API or run the migration command before relying on new fields.</SourceNote>
          )}
        </Panel>

        <Panel title="Scheduler" eyebrow="BACKGROUND COLLECTION">
          {scheduler.enabled === false ? (
            <p className="ws-muted">
              Background scheduling is disabled in configuration. Collection only happens when triggered manually.
            </p>
          ) : (
            <dl className="ws-facts">
              <div><dt>Enabled</dt><dd>{scheduler.enabled ? "yes" : "no"}</dd></div>
              <div><dt>Currently running</dt><dd>{(scheduler.running || []).length ? scheduler.running.join(", ") : "none"}</dd></div>
              {scheduler.tick_seconds != null && <div><dt>Tick</dt><dd>{formatNumber(scheduler.tick_seconds)} s</dd></div>}
            </dl>
          )}
          {(scheduler.jobs || []).length > 0 && (
            <ul className="ws-compact-list">
              {scheduler.jobs.map((job) => (
                <li key={job.provider}>
                  <strong>{job.provider}</strong>
                  <Badge tone={job.enabled ? "ok" : "muted"}>{job.enabled ? "scheduled" : "not scheduled"}</Badge>
                  <span className="ws-muted">every {formatNumber((job.interval_seconds || 0) / 60)} min</span>
                  {job.next_run_at && <span className="ws-muted">next {formatDateTime(job.next_run_at)}</span>}
                </li>
              ))}
            </ul>
          )}
          <SourceNote>
            Ingestion now: {ingestion.data?.running ? "a collection is running" : "idle"} ·{" "}
            {formatNumber((ingestion.data?.enabled_providers || []).length)} providers enabled.
          </SourceNote>
        </Panel>
      </div>

      <div className="ws-grid-2">
        <Panel title="AI capabilities" eyebrow="OLLAMA / RAG">
          <dl className="ws-facts">
            <div><dt>AI ingestion</dt><dd>{data?.ai?.ingestion_enabled ? "enabled" : "disabled"}</dd></div>
            <div><dt>AI classification</dt><dd>{data?.ai?.classification_enabled ? "enabled" : "disabled"}</dd></div>
            <div><dt>Retrieval assistant</dt><dd>{data?.ai?.rag_enabled ? "enabled" : "disabled"}</dd></div>
          </dl>
          <SourceNote>
            When AI is disabled the platform still classifies, scores and clusters deterministically. AI output is
            always labelled as an assessment, never as verified fact.
          </SourceNote>
        </Panel>

        <Panel title="Security posture" eyebrow="EXPOSURE FLAGS">
          <dl className="ws-facts">
            <div>
              <dt>Demo data</dt>
              <dd>
                {data?.security?.demo_data_enabled ? (
                  <Badge tone="danger">enabled — seed endpoint reachable</Badge>
                ) : (
                  <Badge tone="ok">disabled</Badge>
                )}
              </dd>
            </div>
            <div><dt>Private hosts reachable</dt><dd>{data?.security?.ssrf_private_hosts_allowed ? "yes (unsafe)" : "no (SSRF protection active)"}</dd></div>
            <div>
              <dt>CORS origins</dt>
              <dd>{(data?.security?.cors_origins || []).length ? data.security.cors_origins.join(", ") : "none configured"}</dd>
            </div>
          </dl>
          <SourceNote tone="warn">
            Demo data must stay disabled outside development: the seed endpoint writes example events into the
            database.
          </SourceNote>
        </Panel>
      </div>

      <Panel title="Intelligence gaps" eyebrow={`${formatNumber(gaps.data?.count ?? 0)} CURRENT GAPS`}>
        <p className="ws-muted ws-small">{gaps.data?.caveat || "Coverage gap status is unavailable."}</p>
        {(gaps.data?.gaps || []).length ? <ul className="ws-compact-list">{gaps.data.gaps.slice(0, 12).map((gap, index) => <li key={`${gap.type}-${gap.provider || gap.category}-${index}`}><Badge tone={gap.status === "error" ? "danger" : "warn"}>{gap.type}</Badge><span>{gap.provider || gap.category}</span><span className="ws-muted">{gap.detail}</span></li>)}</ul> : <p className="ws-muted ws-small">No gaps found in current stored data.</p>}
      </Panel>

      <Panel title="Recent collection runs" eyebrow="ALL PROVIDERS">
        {(ingestion.data?.recent_runs || []).length === 0 ? (
          <Empty title="No collection runs recorded" />
        ) : (
          <ul className="ws-compact-list">
            {ingestion.data.recent_runs.map((run) => (
              <li key={run.id}>
                <strong>{run.provider_key}</strong>
                <span className="ws-muted">{run.started_at ? formatDateTime(run.started_at) : "—"}</span>
                <Badge tone={run.status === "healthy" ? "ok" : run.status === "degraded" ? "warn" : "danger"}>{run.status}</Badge>
                <span className="ws-muted">
                  {formatNumber(run.records_received)} records · {formatNumber(run.events_created)} events
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
