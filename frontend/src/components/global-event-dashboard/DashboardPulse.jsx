export default function DashboardPulse({ summary, total }) {
  const metrics = [
    { label: "Historical events", value: total, tone: "blue" },
    { label: "Major signals", value: summary.majorEvents, tone: "red" },
    { label: "Countries", value: summary.countries, tone: "green" },
    { label: "Themes", value: summary.categories, tone: "violet" },
  ];

  return (
    <div className="dashboard-pulse" aria-label="Filtered event summary">
      {metrics.map((metric) => (
        <div className={`pulse-item pulse-${metric.tone}`} key={metric.label}>
          <strong>{metric.value}</strong>
          <span>{metric.label}</span>
        </div>
      ))}
    </div>
  );
}
