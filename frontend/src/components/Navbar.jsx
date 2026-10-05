import { useEffect, useRef, useState } from "react";

import useScrolled from "../hooks/useScrolled";

export default function Navbar({
  activeView = "overview",
  onOverview,
  onDashboard,
  onWeather,
  onAssistant,
  onCollect,
  collecting,
  user,
  onLogout,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const accountRef = useRef(null);
  const scrolled = useScrolled();

  const navItems = [
    { id: "overview", label: "Overview", icon: "◎", action: onOverview },
    { id: "dashboard", label: "Analytics", icon: "▤", action: onDashboard },
    { id: "weather", label: "Weather", icon: "☁", action: onWeather },
    { id: "assistant", label: "AI Assistant", icon: "✦", action: onAssistant },
  ];

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

  return (
    <nav className={scrolled ? "site-navbar is-scrolled" : "site-navbar"} aria-label="Main">
      <div className="navbar-inner">
        <button className="navbar-brand" onClick={onOverview} aria-label="Global Event Intelligence home">
          <span className="navbar-orbit" aria-hidden="true"><i /><i /><i /></span>
          <span>
            <strong>Global Intelligence</strong>
            <small>EVENT MONITORING PLATFORM</small>
          </span>
        </button>

        <div className="navbar-links" role="group" aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeView === item.id ? "nav-link active" : "nav-link"}
              aria-current={activeView === item.id ? "page" : undefined}
              onClick={item.action}
            >
              <span className="nav-link-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>

        <div className="navbar-actions">
          <button className="navbar-collect" onClick={onCollect} disabled={collecting}>
            <span className={collecting ? "spin" : ""} aria-hidden="true">↻</span>
            {collecting ? "Collecting" : "Collect News"}
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
