import { useEffect, useMemo, useRef, useState } from "react";

import { unifiedSearch } from "../../services/api.jsx";
import { workspaceSections } from "../../navigation/workspaceNav";

/**
 * Global search / command palette (Ctrl/Cmd-K).
 *
 * Commands navigate; searches come from /api/search, which queries stored
 * events, entities, countries and articles. Nothing is suggested that the
 * backend did not return.
 */
export default function CommandPalette({ open, onClose, onNavigate, onOpenEvent, onOpenCountry }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults(null);
      setError("");
      setCursor(0);
      return;
    }
    const timer = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    if (query.trim().length < 2) {
      setResults(null);
      setError("");
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const data = await unifiedSearch(query.trim());
        if (!cancelled) {
          setResults(data);
          setError("");
        }
      } catch (caught) {
        if (!cancelled) {
          setResults(null);
          setError(caught?.response?.data?.detail || "Search failed.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const commands = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return workspaceSections
      .filter((section) => !needle || section.label.toLowerCase().includes(needle))
      .map((section) => ({
        kind: "command",
        key: `cmd-${section.id}`,
        label: `Go to ${section.label}`,
        run: () => onNavigate(section.id),
      }));
  }, [query, onNavigate]);

  const searchItems = useMemo(() => {
    if (!results) return [];
    const open = (fn) => fn;
    return [
      ...results.events.map((event) => ({
        kind: "event",
        key: `event-${event.id}`,
        label: event.title,
        detail: [event.category?.replace(/_/g, " "), event.country_code, event.severity != null ? `severity ${event.severity}` : null]
          .filter(Boolean)
          .join(" · "),
        run: () => open(onOpenEvent)(event),
      })),
      ...results.countries.map((country) => ({
        kind: "country",
        key: `country-${country.country_code}`,
        label: country.country,
        detail: "Country intelligence",
        run: () => open(onOpenCountry)(country),
      })),
      ...results.entities.map((entity) => ({
        kind: "entity",
        key: `entity-${entity.id}`,
        label: entity.name,
        detail: `${entity.entity_type} · ${entity.mention_count} mentions`,
        run: () => onNavigate("entities", { entity: entity.id }),
      })),
      ...results.articles.map((article) => ({
        kind: "source",
        key: `article-${article.id}`,
        label: article.title || article.url,
        detail: `${article.publisher || "source"} · ${article.published_at || "time unknown"}`,
        href: article.url,
        run: () => window.open(article.url, "_blank", "noopener,noreferrer"),
      })),
    ];
  }, [results, onNavigate, onOpenEvent, onOpenCountry]);

  const items = [...commands, ...searchItems];

  useEffect(() => {
    setCursor(0);
  }, [query, results]);

  if (!open) return null;

  const choose = (item) => {
    if (!item) return;
    item.run();
    onClose();
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((value) => Math.min(value + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(items[cursor]);
    }
  };

  return (
    <div className="ws-palette-backdrop" role="presentation" onClick={onClose}>
      <div
        className="ws-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search and commands"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="ws-palette-field">
          <span aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search events, countries, entities, sources — or jump to a section"
            aria-label="Search query"
            aria-controls="command-results"
            aria-activedescendant={items[cursor] ? `cmd-item-${items[cursor].key}` : undefined}
            autoComplete="off"
          />
          <kbd>Esc</kbd>
        </div>

        <div className="ws-palette-results" id="command-results" role="listbox" aria-label="Results">
          {loading && <p className="ws-palette-note">Searching stored reporting…</p>}
          {error && <p className="ws-palette-note ws-error-text">{error}</p>}
          {!loading && !error && query.trim().length >= 2 && items.length === 0 && (
            <p className="ws-palette-note">No stored events, entities, countries or sources match “{query}”.</p>
          )}
          {items.map((item, index) => (
            <button
              key={item.key}
              id={`cmd-item-${item.key}`}
              type="button"
              role="option"
              aria-selected={index === cursor}
              className={`ws-palette-item ${index === cursor ? "is-active" : ""}`}
              onMouseEnter={() => setCursor(index)}
              onClick={() => choose(item)}
            >
              <span className="ws-palette-kind">{item.kind}</span>
              <span className="ws-palette-label">{item.label}</span>
              {item.detail && <span className="ws-palette-detail">{item.detail}</span>}
            </button>
          ))}
        </div>

        <footer className="ws-palette-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span>Results come from stored reporting only.</span>
        </footer>
      </div>
    </div>
  );
}
