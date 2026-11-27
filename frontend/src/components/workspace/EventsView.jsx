import { useCallback, useEffect, useMemo, useState } from "react";

import { getEventsPage, getSavedSearches, createSavedSearch, deleteSavedSearch, getTaxonomy } from "../../services/api.jsx";
import { formatCount, formatNumber } from "../../services/format.jsx";
import { Badge, DataTable, Empty, ErrorState, Loading, Panel, Toolbar } from "./primitives.jsx";
import EventRow from "./EventRow.jsx";

const SORTS = [
  { id: "recent", label: "Most recent" },
  { id: "priority", label: "Highest priority" },
  { id: "severity", label: "Highest severity" },
  { id: "confidence", label: "Best evidenced" },
];

const STATES = ["developing", "escalating", "stable", "de_escalating", "resolved", "archived"];

const FILTER_LABELS = {
  category: "Category",
  subcategory: "Subcategory",
  country_code: "Country",
  min_severity: "Min severity",
  min_confidence: "Min confidence",
  event_state: "State",
  provider: "Provider",
  search: "Search",
  sort: "Sort",
};

const defaultFilters = {
  category: "",
  subcategory: "",
  country_code: "",
  min_severity: "",
  min_confidence: "",
  event_state: "",
  provider: "",
  search: "",
  sort: "recent",
};

/**
 * Event queue with server-side filtering and cursor pagination.
 *
 * The page never downloads the whole history: the API returns 50 rows and a
 * cursor, and the count shown is the number of rows actually loaded.
 */
export default function EventsView({ initialFilters, onSelectEvent, onNavigate }) {
  const [filters, setFilters] = useState({ ...defaultFilters, ...(initialFilters || {}) });
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState([]);
  const [taxonomy, setTaxonomy] = useState(null);
  const [saveName, setSaveName] = useState("");
  const [savedError, setSavedError] = useState("");

  useEffect(() => {
    if (initialFilters) setFilters((current) => ({ ...current, ...initialFilters }));
  }, [initialFilters]);

  const params = useMemo(() => {
    const out = { sort: filters.sort, limit: 50 };
    ["category", "subcategory", "country_code", "event_state", "provider", "search"].forEach((key) => {
      if (filters[key]) out[key] = filters[key];
    });
    if (filters.min_severity !== "") out.min_severity = Number(filters.min_severity);
    if (filters.min_confidence !== "") out.min_confidence = Number(filters.min_confidence);
    return out;
  }, [filters]);

  const load = useCallback(async (nextCursor = null, replace = true) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getEventsPage({ ...params, cursor: nextCursor || undefined });
      setItems((current) => (replace ? data.items : [...current, ...data.items]));
      setCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => {
    load(null, true);
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSavedSearches(), getTaxonomy()])
      .then(([savedData, taxonomyData]) => {
        if (cancelled) return;
        setSaved(savedData.items || []);
        setTaxonomy(taxonomyData);
      })
      .catch(() => {
        /* Saved searches are optional: a failure must not block the queue. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = (key, value) => setFilters((current) => ({ ...current, [key]: value }));

  const activeChips = Object.entries(filters).filter(
    ([key, value]) => key !== "sort" && value !== "" && value !== null && value !== undefined
  );

  const saveCurrent = async () => {
    const name = saveName.trim() || `View ${new Date().toLocaleString()}`;
    try {
      const created = await createSavedSearch({ name, filters: params });
      setSaved((current) => [{ id: created.id, name, filters: params }, ...current]);
      setSaveName("");
      setSavedError("");
    } catch (caught) {
      setSavedError(caught?.response?.data?.detail || "Saving the view failed.");
    }
  };

  const removeSaved = async (id) => {
    try {
      await deleteSavedSearch(id);
      setSaved((current) => current.filter((entry) => entry.id !== id));
    } catch (caught) {
      setSavedError(caught?.response?.data?.detail || "Deleting the saved view failed.");
    }
  };

  const categories = taxonomy?.categories || [];

  return (
    <div className="ws-view ws-events">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">EVENT QUEUE</p>
          <h1>Events</h1>
          <p className="ws-subtitle">
            Server-side filtering and cursor pagination. Severity, confidence and priority are shown separately because
            they answer different questions.
          </p>
        </div>
        <div className="ws-head-meta">
          <span className="ws-muted">{formatCount(items.length, "row")} loaded</span>
        </div>
      </header>

      <Panel className="ws-filter-panel">
        <Toolbar>
          <label className="ws-field ws-field-grow">
            <span>Search title and summary</span>
            <input
              type="search"
              value={filters.search}
              placeholder="e.g. flood, election, ceasefire"
              onChange={(event) => update("search", event.target.value)}
            />
          </label>
          <label className="ws-field">
            <span>Category</span>
            <select value={filters.category} onChange={(event) => update("category", event.target.value)}>
              <option value="">All categories</option>
              {categories.map((category) => (
                <option key={category.key || category.id || category.name} value={category.key || category.id || category.name}>
                  {category.label || category.name || category.key}
                </option>
              ))}
            </select>
          </label>
          <label className="ws-field">
            <span>State</span>
            <select value={filters.event_state} onChange={(event) => update("event_state", event.target.value)}>
              <option value="">Any state</option>
              {STATES.map((state) => (
                <option key={state} value={state}>{state.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="ws-field">
            <span>Sort</span>
            <select value={filters.sort} onChange={(event) => update("sort", event.target.value)}>
              {SORTS.map((sort) => (
                <option key={sort.id} value={sort.id}>{sort.label}</option>
              ))}
            </select>
          </label>
          <label className="ws-field ws-field-narrow">
            <span>Min severity</span>
            <input
              type="number" min="0" max="10" step="0.5" value={filters.min_severity}
              onChange={(event) => update("min_severity", event.target.value)}
            />
          </label>
          <label className="ws-field ws-field-narrow">
            <span>Min confidence</span>
            <input
              type="number" min="0" max="1" step="0.05" value={filters.min_confidence}
              onChange={(event) => update("min_confidence", event.target.value)}
            />
          </label>
          <label className="ws-field ws-field-narrow">
            <span>Country code</span>
            <input
              maxLength={2} placeholder="JP" value={filters.country_code}
              onChange={(event) => update("country_code", event.target.value.toUpperCase())}
            />
          </label>
          <button type="button" className="ws-button" onClick={() => setFilters({ ...defaultFilters })}>
            Reset
          </button>
        </Toolbar>

        {activeChips.length > 0 && (
          <div className="ws-chip-row">
            {activeChips.map(([key, value]) => (
              <button
                key={key}
                type="button"
                className="ws-filter-chip"
                onClick={() => update(key, "")}
                aria-label={`Remove filter ${FILTER_LABELS[key]}: ${value}`}
              >
                {FILTER_LABELS[key] || key}: {String(value)} <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      <div className="ws-grid-main-aside">
        <Panel title="Results" eyebrow={`SORTED BY ${SORTS.find((s) => s.id === filters.sort)?.label.toUpperCase()}`}>
          {error ? (
            <ErrorState error={error} onRetry={() => load(null, true)} />
          ) : loading && items.length === 0 ? (
            <Loading label="Loading events" />
          ) : items.length === 0 ? (
            <Empty title="No events match these filters">
              The queue is built from stored reporting. Relax the filters, or run a collection to bring in new data.
            </Empty>
          ) : (
            <>
              <div className="ws-event-list">
                {items.map((event) => (
                  <EventRow key={event.id} event={event} onSelect={onSelectEvent} />
                ))}
              </div>
              <div className="ws-pager">
                {hasMore ? (
                  <button type="button" className="ws-button" onClick={() => load(cursor, false)} disabled={loading}>
                    {loading ? "Loading…" : "Load more"}
                  </button>
                ) : (
                  <span className="ws-muted">End of results for these filters.</span>
                )}
              </div>
            </>
          )}
        </Panel>

        <div className="ws-stack">
          <Panel title="Saved views" eyebrow="REUSABLE FILTER SETS">
            {savedError && <p className="ws-error-text">{savedError}</p>}
            {saved.length === 0 ? (
              <p className="ws-muted ws-small">No saved views yet. Save the current filters to reuse them later.</p>
            ) : (
              <ul className="ws-saved-list">
                {saved.map((view) => {
                  const viewParams = typeof view.filters === "string" ? safeParse(view.filters) : view.filters || {};
                  return (
                    <li key={view.id}>
                      <button type="button" className="ws-link" onClick={() => setFilters({ ...defaultFilters, ...viewParams })}>
                        {view.name}
                      </button>
                      <button type="button" className="ws-icon-button" onClick={() => removeSaved(view.id)} aria-label={`Delete ${view.name}`}>×</button>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="ws-inline-form">
              <input
                value={saveName}
                onChange={(event) => setSaveName(event.target.value)}
                placeholder="Name this view"
                aria-label="Name this view"
              />
              <button type="button" className="ws-button" onClick={saveCurrent}>Save</button>
            </div>
          </Panel>

          {taxonomy && (
            <Panel title="Taxonomy" eyebrow={`VERSION ${taxonomy.version || "—"}`}>
              <p className="ws-muted ws-small">
                Classification uses this hierarchy. AI only refines a category the deterministic keyword pass could not
                resolve, and the method is stored on every event.
              </p>
              <div className="ws-chip-row">
                {(taxonomy.categories || []).slice(0, 18).map((category) => (
                  <button
                    key={category.key || category.id || category.name}
                    type="button"
                    className="ws-filter-chip"
                    onClick={() => update("category", category.key || category.id || category.name)}
                  >
                    {category.label || category.key}
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function safeParse(value) {
  try {
    return JSON.parse(value || "{}");
  } catch {
    return {};
  }
}
