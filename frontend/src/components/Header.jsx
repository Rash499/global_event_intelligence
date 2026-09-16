export default function Header({ onCollect, loading }) {
  return (
    <header className="app-header">
      <div className="header-content">
        <div>
          <p className="eyebrow">AI GLOBAL EVENT INTELLIGENCE</p>

          <h1>World Event Map</h1>

          <p className="subtitle">
            Monitor important events happening around the world in real time.
          </p>
        </div>

        <button
          className="collect-button"
          onClick={onCollect}
          disabled={loading}
        >
          {loading ? "Collecting..." : "Collect News"}
        </button>
      </div>
    </header>
  );
}