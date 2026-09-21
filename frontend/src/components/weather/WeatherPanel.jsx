const severityClass = (severity = "normal") => severity.toLowerCase();

function scoreLabel(score) {
  if (score >= 81) return "Extreme";
  if (score >= 61) return "High";
  if (score >= 41) return "Moderate";
  if (score >= 21) return "Low";
  return "Normal";
}

export default function WeatherPanel({ weather, onSelect }) {
  const critical = [...weather]
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 12);

  return (
    <aside className="latest-panel weather-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">WEATHER INTELLIGENCE</p>
          <h2>Critical Areas</h2>
        </div>
        <span>{weather.length}</span>
      </div>

      <p className="weather-panel-note">
        Score combines current conditions with the highest forecast severity
        across the available forecast period. It is an application severity
        index, not an official warning level.
      </p>

      <div className="weather-list">
        {critical.map((item) => (
          <button
            type="button"
            className="weather-row"
            key={`${item.country_code}-${item.latitude}-${item.longitude}`}
            onClick={() => onSelect(item)}
          >
            <span className={`weather-score ${severityClass(item.severity)}`}>
              {Math.round(item.score || 0)}
            </span>
            <span className="weather-row-copy">
              <strong>{item.country || item.country_code || "Unknown"}</strong>
              <small>
                {item.current?.temperature_2m ?? "—"}°C · {item.current?.weather_description || "Unknown"}
              </small>
            </span>
            <span className={`weather-severity ${severityClass(item.severity)}`}>
              {item.severity || scoreLabel(item.score)}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
