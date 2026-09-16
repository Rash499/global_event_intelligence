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
    <section className="stats">
      <div className="stat-card">
        <strong>{events.length}</strong>
        <span>Events Loaded</span>
      </div>

      <div className="stat-card">
        <strong>{majorEvents}</strong>
        <span>Major Events</span>
      </div>

      <div className="stat-card">
        <strong>{countries}</strong>
        <span>Countries</span>
      </div>

      <div className="stat-card">
        <strong>{categories}</strong>
        <span>Categories</span>
      </div>
    </section>
  );
}