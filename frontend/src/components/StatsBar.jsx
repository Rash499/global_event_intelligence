export default function StatsBar({ events }) {
  const majorEvents = events.filter(
    (event) => event.importance >= 8
  ).length;

  const countries = new Set(
    events
      .map((event) => event.country_code)
      .filter(Boolean)
  ).size;

  const categories = new Set(
    events
      .map((event) => event.category)
      .filter(Boolean)
  ).size;

  return (
    <section className="stats" aria-label="Global event summary">
      <div className="stat-card stat-card-events">
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">◈</span>
          <span className="stat-kicker">Live index</span>
        </div>
        <strong>{events.length}</strong>
        <span>Events loaded</span>
        <small>Across the current feed</small>
      </div>

      <div className="stat-card stat-card-major">
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">!</span>
          <span className="stat-kicker">Priority</span>
        </div>
        <strong>{majorEvents}</strong>
        <span>Major events</span>
        <small>Importance score 8+</small>
      </div>

      <div className="stat-card stat-card-countries">
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">◎</span>
          <span className="stat-kicker">Reach</span>
        </div>
        <strong>{countries}</strong>
        <span>Countries</span>
        <small>Geographies represented</small>
      </div>

      <div className="stat-card stat-card-categories">
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">⌘</span>
          <span className="stat-kicker">Signal mix</span>
        </div>
        <strong>{categories}</strong>
        <span>Categories</span>
        <small>Distinct event themes</small>
      </div>
    </section>
  );
}