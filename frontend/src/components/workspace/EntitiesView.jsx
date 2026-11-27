import { useState } from "react";

import { getEntities, getEntity } from "../../services/api.jsx";
import { formatDateTime } from "../../services/dateFormat.jsx";
import { formatCount, formatNumber, severityColour } from "../../services/format.jsx";
import useApiResource from "../../hooks/useApiResource";
import { Badge, DataTable, Empty, ErrorState, Loading, Panel, SourceNote } from "./primitives.jsx";

const TYPES = ["", "country", "organization", "person", "location", "event", "other"];

/**
 * Entity intelligence.
 *
 * Entities are extracted from collected reporting, so mention counts reflect
 * coverage, not importance. Relationships are shown with the confidence the
 * extractor recorded.
 */
export default function EntitiesView({ initialSelection, onSelectEvent }) {
  const [type, setType] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(initialSelection?.entity ?? null);

  const list = useApiResource(() => getEntities({ entity_type: type || undefined, q: query || undefined, limit: 100 }), [type, query]);
  const detail = useApiResource(() => getEntity(selected), [selected], { enabled: Boolean(selected) });

  return (
    <div className="ws-view ws-entities">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">ENTITY INTELLIGENCE</p>
          <h1>Actors & entities</h1>
          <p className="ws-subtitle">
            Extracted from collected reporting with the source text. Mention counts measure coverage, not importance.
          </p>
        </div>
      </header>

      <div className="ws-grid-main-aside">
        <Panel
          title="Entities"
          eyebrow={formatCount(list.data?.count ?? 0, "entity", "entities")}
        >
          <div className="ws-toolbar">
            <label className="ws-field ws-field-grow">
              <span>Search</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search entity names" />
            </label>
            <label className="ws-field">
              <span>Type</span>
              <select value={type} onChange={(event) => setType(event.target.value)}>
                {TYPES.map((option) => (
                  <option key={option || "all"} value={option}>{option ? option : "All types"}</option>
                ))}
              </select>
            </label>
          </div>

          {list.error ? (
            <ErrorState error={list.error} onRetry={list.reload} />
          ) : list.loading && !list.data ? (
            <Loading label="Loading entities" />
          ) : (
            <DataTable
              empty="No entities match these filters"
              rows={list.data?.items || []}
              rowKey={(row) => row.id}
              onRowClick={(row) => setSelected(row.id)}
              columns={[
                {
                  key: "name",
                  label: "Name",
                  render: (row) => (
                    <button type="button" className="ws-link" onClick={() => setSelected(row.id)}>{row.name}</button>
                  ),
                },
                { key: "entity_type", label: "Type", render: (row) => <Badge>{row.entity_type}</Badge> },
                { key: "country_code", label: "Country", render: (row) => row.country_code || "—" },
                { key: "mention_count", label: "Mentions", align: "right", render: (row) => formatNumber(row.mention_count) },
              ]}
            />
          )}
          <SourceNote>
            Entity extraction is deterministic (gazetteer and pattern based). Alternative spellings are folded into
            aliases; the canonical name is what you see here.
          </SourceNote>
        </Panel>

        <div className="ws-stack">
          {!selected ? (
            <Empty title="Select an entity">Pick an entity to see its events, aliases and relationships.</Empty>
          ) : detail.error ? (
            <ErrorState error={detail.error} onRetry={detail.reload} title="Entity could not be loaded" />
          ) : detail.loading && !detail.data ? (
            <Loading label="Loading entity" />
          ) : (
            <>
              <Panel title={detail.data.name} eyebrow={String(detail.data.entity_type || "").toUpperCase()}>
                {detail.data.description && <p className="ws-body-text">{detail.data.description}</p>}
                <dl className="ws-facts">
                  <div><dt>Mentions</dt><dd>{formatNumber(detail.data.mention_count)}</dd></div>
                  {detail.data.country_code && <div><dt>Country</dt><dd>{detail.data.country_code}</dd></div>}
                  {detail.data.first_seen_at && <div><dt>First seen</dt><dd>{formatDateTime(detail.data.first_seen_at)}</dd></div>}
                  {detail.data.last_seen_at && <div><dt>Last seen</dt><dd>{formatDateTime(detail.data.last_seen_at)}</dd></div>}
                </dl>
                {(detail.data.aliases || []).length > 0 && (
                  <div className="ws-chip-row">
                    {detail.data.aliases.map((alias) => <Badge key={alias}>{alias}</Badge>)}
                  </div>
                )}
              </Panel>

              <Panel title="Related entities" eyebrow="CO-MENTION / RELATIONSHIP">
                {(detail.data.relationships || []).length === 0 ? (
                  <p className="ws-muted ws-small">No relationships stored for this entity.</p>
                ) : (
                  <ul className="ws-compact-list">
                    {detail.data.relationships.map((relation) => (
                      <li key={`${relation.entity_id}-${relation.relationship}`}>
                        <button type="button" className="ws-link" onClick={() => setSelected(relation.entity_id)}>
                          {relation.name}
                        </button>
                        <Badge>{relation.relationship}</Badge>
                        <span className="ws-muted">match {formatNumber((relation.confidence || 0) * 100, 0)}%</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title="Events mentioning this entity" eyebrow="EVIDENCE">
                {(detail.data.events || []).length === 0 ? (
                  <Empty title="No linked events" />
                ) : (
                  <ul className="ws-compact-list">
                    {detail.data.events.map((event) => (
                      <li key={event.id}>
                        <button type="button" className="ws-link" onClick={() => onSelectEvent?.({ id: event.id, event })}>
                          {event.title}
                        </button>
                        <span className="ws-muted">
                          {event.severity != null ? (
                            <Badge colour={severityColour(event.severity)}>severity {formatNumber(event.severity, 1)}</Badge>
                          ) : "not assessed"}
                          {event.role ? ` · ${event.role}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
