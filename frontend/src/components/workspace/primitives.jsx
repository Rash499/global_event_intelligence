/**
 * Shared workspace primitives.
 *
 * Every number rendered through these components comes from the API. When the
 * API has no value, the component says so ("not assessed") instead of showing
 * a zero or a placeholder figure, and every score can be opened to show the
 * evidence it was computed from.
 */
import { useState } from "react";

import { formatCount, formatNumber } from "../../services/format.jsx";

export function Panel({ title, eyebrow, actions, children, className = "", footer, as: Tag = "section" }) {
  return (
    <Tag className={`ws-panel ${className}`.trim()}>
      {(title || actions) && (
        <header className="ws-panel-head">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && <h2>{title}</h2>}
          </div>
          {actions && <div className="ws-panel-actions">{actions}</div>}
        </header>
      )}
      <div className="ws-panel-body">{children}</div>
      {footer && <footer className="ws-panel-foot">{footer}</footer>}
    </Tag>
  );
}

export function Stat({ label, value, hint, tone = "default", format }) {
  const rendered =
    value === null || value === undefined
      ? "—"
      : typeof value === "number" && format === "count"
        ? formatCount(value, hint || "record")
        : typeof value === "number"
          ? formatNumber(value)
          : value;
  return (
    <div className={`ws-stat tone-${tone}`}>
      <span className="ws-stat-label">{label}</span>
      <strong className="ws-stat-value">{rendered}</strong>
      {hint && typeof value === "number" && format === "count" ? null : hint ? (
        <span className="ws-stat-hint">{hint}</span>
      ) : null}
    </div>
  );
}

export function Badge({ children, colour, title, tone }) {
  const style = colour ? { "--badge-colour": colour } : undefined;
  return (
    <span className={`ws-badge ${tone ? `tone-${tone}` : ""}`.trim()} style={style} title={title}>
      {children}
    </span>
  );
}

export function Meter({ value, max = 10, colour = "#42c9ff", label, caption }) {
  const safe = Math.max(0, Math.min(Number(value) || 0, max));
  const pct = (safe / max) * 100;
  return (
    <div className="ws-meter" role="group" aria-label={label}>
      <div className="ws-meter-track">
        <span className="ws-meter-fill" style={{ width: `${pct}%`, background: colour }} />
      </div>
      {caption && <span className="ws-meter-caption">{caption}</span>}
    </div>
  );
}

/** Collapsible "why is this score what it is" block. */
export function Explain({ summary = "How this was scored", children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details className="ws-explain" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{summary}</summary>
      <div className="ws-explain-body">{children}</div>
    </details>
  );
}

export function Breakdown({ components, labels, max = 10 }) {
  if (!components || !Object.keys(components).length) {
    return <p className="ws-muted">No component breakdown was stored for this score.</p>;
  }
  const entries = Object.entries(components)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .sort((a, b) => b[1] - a[1]);

  return (
    <ul className="ws-breakdown">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span>{labels?.[key] || key.replace(/_/g, " ")}</span>
          <Meter value={value} max={max} caption={formatNumber(value, 2)} />
        </li>
      ))}
    </ul>
  );
}

export function Empty({ title = "Nothing to show", children, icon = "◎" }) {
  return (
    <div className="ws-empty">
      <span aria-hidden="true">{icon}</span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Could not load this data" }) {
  const message =
    error?.response?.data?.detail ||
    error?.message ||
    "The request failed. The backend may not be running.";
  return (
    <div className="ws-error" role="alert">
      <strong>{title}</strong>
      <p>{message}</p>
      {error?.response?.status && <p className="ws-muted">HTTP {error.response.status}</p>}
      {onRetry && (
        <button type="button" className="ws-button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Loading({ label = "Loading data" }) {
  return (
    <div className="ws-loading" role="status" aria-live="polite">
      <span className="ws-spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function DataTable({ columns, rows, rowKey, onRowClick, caption, empty = "No rows" }) {
  if (!rows?.length) return <Empty title={empty} />;
  return (
    <div className="ws-table-wrap">
      <table className="ws-table">
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.align ? `align-${column.align}` : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey ? rowKey(row) : index}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? "is-clickable" : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} className={column.align ? `align-${column.align}` : undefined}>
                  {column.render ? column.render(row) : (row[column.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Toolbar({ children, className = "" }) {
  return <div className={`ws-toolbar ${className}`.trim()}>{children}</div>;
}

export function SourceNote({ children, tone = "muted" }) {
  return (
    <p className={`ws-source-note tone-${tone}`} role="note">
      {children}
    </p>
  );
}

export function UpdatedAt({ value, loading }) {
  if (loading) return <span className="ws-muted">refreshing…</span>;
  if (!value) return null;
  const date = new Date(value);
  return (
    <span className="ws-muted" title={value}>
      updated {Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString()}
    </span>
  );
}
