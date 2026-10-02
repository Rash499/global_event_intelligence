import { useState } from "react";

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

  const navItems = [
    { id: "overview", label: "Overview", action: onOverview },
    { id: "dashboard", label: "Analytics", action: onDashboard },
    { id: "weather", label: "Weather", action: onWeather },
    { id: "assistant", label: "AI Assistant", action: onAssistant },
  ];

  return (
    <nav className="site-navbar">
      <div className="navbar-inner">
        <button className="navbar-brand" onClick={onOverview} aria-label="Global Event Intelligence home">
          <span className="navbar-orbit" aria-hidden="true"><i /><i /><i /></span>
          <span>
            <strong>Global Intelligence</strong>
            <small>EVENT MONITORING PLATFORM</small>
          </span>
        </button>

        <div className="navbar-links" aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={activeView === item.id ? "nav-link active" : "nav-link"}
              onClick={item.action}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="navbar-actions">
          <button className="navbar-collect" onClick={onCollect} disabled={collecting}>
            <span className={collecting ? "spin" : ""}>↻</span>
            {collecting ? "Collecting" : "Collect News"}
          </button>

          <div className="navbar-account">
            <button
              className="account-trigger"
              onClick={() => setMenuOpen((value) => !value)}
              aria-expanded={menuOpen}
            >
              <span className="account-avatar">{(user?.display_name || "U").slice(0, 1).toUpperCase()}</span>
              <span className="account-copy">
                <strong>{user?.display_name || "User"}</strong>
                <small>ONLINE</small>
              </span>
              <span className="account-chevron">⌄</span>
            </button>
            {menuOpen && (
              <div className="account-menu">
                <span>{user?.email}</span>
                <button onClick={onLogout}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
