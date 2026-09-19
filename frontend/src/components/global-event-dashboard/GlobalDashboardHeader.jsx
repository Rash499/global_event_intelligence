export default function GlobalDashboardHeader({ eventCount, hasActiveFilters }) {
  return (
    <div className="dashboard-header">
      <div>
        <p className="eyebrow">GLOBAL INTELLIGENCE</p>
        <h2>Event History</h2>
        <p>Previous events ordered from newest to oldest.</p>
      </div>

      <div className="dashboard-header-status">
        <strong>{eventCount} events</strong>
        <span>{hasActiveFilters ? "Filtered view" : "Full intelligence feed"}</span>
      </div>
    </div>
  );
}
