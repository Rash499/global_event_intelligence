import { useEffect, useRef, useState } from "react";

import useScrolled from "../hooks/useScrolled";
import { workspaceSections } from "../navigation/workspaceNav";
import { useGroupedSections } from "../services/format.jsx";

/**
 * Operations workspace navigation.
 *
 * Sections are grouped (Monitor / Analyse / Deliver / Operate) so the workspace
 * reads as a product rather than a flat list of pages. The health dot reflects
 * the provider status endpoint; it is only shown when the backend reported it.
 */
export default function Navbar({
  activeView = "overview",
  onNavigate,
  onOverview,
  onOpenSearch,
  onCollect,
  collecting,
  providerHealth,
  alertCount = 0,
  user,
  onLogout,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const accountRef = useRef(null);
  const scrolled = useScrolled();
  const groups = useGroupedSections(workspaceSections);

  const go = (id) => {
    setMobileOpen(false);
    if (id === "overview" && onOverview) onOverview();
    else onNavigate?.(id);
  };

  // Close the account menu on outside click or Escape.
  useEffect(() => {
    if (!menuOpen) return undefined;

    const onPointerDown = (event) => {
      if (accountRef.current && !accountRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setMenuOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const healthTone =
    providerHealth?.unavailable > 0 ? "danger" : providerHealth?.degraded > 0 ? "warn" : providerHealth ? "ok" : "unknown";
  const healthLabel = providerHealth
    ? `${providerHealth.healthy || 0} healthy, ${providerHealth.degraded || 0} degraded, ${
        providerHealth.unavailable || 0
      } unavailable, ${providerHealth.not_configured || 0} not configured`
    : "Provider status unknown";

  return (
    <nav className={scrolled ? "site-navbar is-scrolled" : "site-navbar"} aria-label="Workspace">
      <div className="navbar-inner">
        <button className="navbar-brand" onClick={() => go("overview")} aria-label="Global Event Intelligence home">
          <span className="navbar-orbit" aria-hidden="true"><i /><i /><i /></span>
          <span>
            <strong>Global Intelligence</strong>
            <small>OPERATIONS WORKSPACE</small>
          </span>
        </button>

        <button
          type="button"
          className="navbar-burger"
          aria-expanded={mobileOpen}
          aria-controls="workspace-nav-links"
          onClick={() => setMobileOpen((value) => !value)}
        >
          <span aria-hidden="true">☰</span> Sections
        </button>

        <div
          id="workspace-nav-links"
          className={mobileOpen ? "navbar-links is-open" : "navbar-links"}
          role="group"
          aria-label="Primary navigation"
        >
          {groups.map((group) => (
            <div className="nav-group" key={group.name}>
              <span className="nav-group-label" aria-hidden="true">{group.name}</span>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={activeView === item.id ? "nav-link active" : "nav-link"}
                  aria-current={activeView === item.id ? "page" : undefined}
                  onClick={() => go(item.id)}
                  title={item.label}
                >
                  <span className="nav-link-icon" aria-hidden="true">{item.icon}</span>
                  <span className="nav-link-text">{item.label}</span>
                  {item.id === "alerts" && alertCount > 0 && (
                    <span className="nav-link-count" aria-label={`${alertCount} new alerts`}>{alertCount}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>

        <div className="navbar-actions">
          <button
            type="button"
            className="navbar-search"
            onClick={onOpenSearch}
            aria-label="Search events, countries and sources (Cmd+K)"
          >
            <span aria-hidden="true">⌕</span>
            <span className="navbar-search-text">Search</span>
            <kbd>⌘K</kbd>
          </button>

          <button
            type="button"
            className={`navbar-health tone-${healthTone}`}
            onClick={() => go("providers")}
            title={healthLabel}
          >
            <i aria-hidden="true" />
            <span className="sr-only">Provider health: </span>
            {healthTone === "unknown" ? "Feeds" : healthTone === "ok" ? "Feeds OK" : "Feed issues"}
          </button>

          <button className="navbar-collect" onClick={onCollect} disabled={collecting}>
            <span className={collecting ? "spin" : ""} aria-hidden="true">↻</span>
            {collecting ? "Collecting" : "Collect"}
          </button>

          <div className="navbar-account" ref={accountRef}>
            <button
              className="account-trigger"
              onClick={() => setMenuOpen((value) => !value)}
              aria-expanded={menuOpen}
              aria-haspopup="menu"
            >
              <span className="account-avatar">{(user?.display_name || "U").slice(0, 1).toUpperCase()}</span>
              <span className="account-copy">
                <strong>{user?.display_name || "User"}</strong>
                <small>ONLINE</small>
              </span>
              <span className="account-chevron" aria-hidden="true">⌄</span>
            </button>
            {menuOpen && (
              <div className="account-menu" role="menu">
                <span>{user?.email}</span>
                <button role="menuitem" onClick={onLogout}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
