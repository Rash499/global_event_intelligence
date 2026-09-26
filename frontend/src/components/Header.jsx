export default function Header({ onCollect, loading, user, onLogout }) {
  return (
    <header className="app-header">
      <div className="header-content">
        <div className="header-brand">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>

          <div className="header-copy">
            <p className="eyebrow">AI GLOBAL EVENT INTELLIGENCE</p>

            <div className="title-row">
              <h1>World Event Map</h1>
              <span className="live-indicator">
                <span className="live-dot" /> Live feed
              </span>
            </div>

            <p className="subtitle">
              Monitor important events happening around the world in real time.
            </p>
          </div>
        </div>

        <div className="header-actions">
          <div className="account-label">
            <strong>{user?.display_name}</strong>
            <span>{user?.email}</span>
          </div>
          <button
            className="collect-button"
            onClick={onCollect}
            disabled={loading}
          >
            <span className="collect-icon" aria-hidden="true">
              {loading ? "..." : "↻"}
            </span>
            <span>{loading ? "Collecting..." : "Collect News"}</span>
          </button>
          <button className="logout-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </div>

      <div className="header-meta" aria-label="Feed status">
        <span><i className="meta-signal" /> Multi-source monitoring</span>
        <span>Auto-check on page load</span>
        <span>Global coverage</span>
      </div>
    </header>
  );
}