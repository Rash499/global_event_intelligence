export default function GlobalDashboardHeader({ eventCount, hasActiveFilters }) {
  return (
    <div className="dashboard-header">
      <div>
        <p className="eyebrow">GLOBAL INTELLIGENCE</p>
        <h2>All Events</h2>
        <p>Explore global events using category, country and importance filters.</p>
      </div>

      <div className="dashboard-header-status">
        <strong>{eventCount} events</strong>
        <span>{hasActiveFilters ? "Filtered view" : "Full intelligence feed"}</span>
      </div>
    </div>
  );
}
