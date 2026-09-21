const severityClass = (severity = "normal") => severity.toLowerCase();

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(date);
};

function RiskBar({ label, value }) {
  return (
    <div className="risk-factor">
      <div className="risk-factor-heading">
        <span>{label}</span>
        <strong>{Math.round(value || 0)}</strong>
      </div>
      <div className="risk-bar">
        <span style={{ width: `${Math.min(100, Math.max(0, value || 0))}%` }} />
      </div>
    </div>
  );
}

export default function WeatherDashboard({ weather, onBack }) {
  if (!weather) return null;

  const daily = weather.daily || [];
  const factors = weather.risk_factors || {};

  return (
    <section className="weather-dashboard">
      <header className="weather-dashboard-header">
        <button className="back-button" onClick={onBack}>
          ← Back to weather map
        </button>

        <div>
          <span className="country-code">{weather.country_code || "GLOBAL"} / WEATHER BRIEF</span>
          <h2>{weather.country || "Weather Area"}</h2>
          <p>
            Current conditions and forecast severity for this location.
          </p>
        </div>

        <div className={`weather-dashboard-score ${severityClass(weather.severity)}`}>
          <strong>{Math.round(weather.score || 0)}</strong>
          <span>{weather.severity}</span>
        </div>
      </header>

      <div className="weather-current-grid">
        <div className="weather-current-card">
          <span>Current condition</span>
          <strong>{weather.current?.weather_description || "—"}</strong>
          <small>
            {weather.current?.temperature_2m ?? "—"}°C · Feels like {weather.current?.apparent_temperature ?? "—"}°C
          </small>
        </div>
        <div className="weather-current-card">
          <span>Precipitation</span>
          <strong>{weather.current?.precipitation ?? "—"} mm</strong>
          <small>{weather.current?.precipitation_probability ?? "—"}% probability</small>
        </div>
        <div className="weather-current-card">
          <span>Wind</span>
          <strong>{weather.current?.wind_speed_10m ?? "—"} km/h</strong>
          <small>Gusts {weather.current?.wind_gusts_10m ?? "—"} km/h</small>
        </div>
        <div className="weather-current-card">
          <span>Forecast peak</span>
          <strong>{Math.round(weather.forecast_score || 0)} / 100</strong>
          <small>Highest daily severity</small>
        </div>
      </div>

      <div className="weather-dashboard-grid">
        <div className="weather-section">
          <div className="weather-section-heading">
            <div>
              <span className="section-eyebrow">RISK BREAKDOWN</span>
              <h3>Why this area is ranked here</h3>
            </div>
          </div>

          <div className="risk-factors">
            <RiskBar label="Temperature" value={factors.temperature} />
            <RiskBar label="Precipitation" value={factors.precipitation} />
            <RiskBar label="Wind" value={factors.wind} />
            <RiskBar label="Severe weather" value={factors.severe_weather} />
          </div>

          <p className="weather-disclaimer">
            This score is calculated from forecast variables and is intended for
            visualization and prioritization. It does not replace official
            meteorological warnings.
          </p>
        </div>

        <div className="weather-section">
          <div className="weather-section-heading">
            <div>
              <span className="section-eyebrow">FORECAST</span>
              <h3>Next {daily.length} days</h3>
            </div>
          </div>

          <div className="forecast-list">
            {daily.map((day) => (
              <div className="forecast-card" key={day.date}>
                <strong>{formatDate(day.date)}</strong>
                <span>{day.weather_description}</span>
                <b>{day.temperature_max}° / {day.temperature_min}°C</b>
                <small>{day.precipitation_probability_max}% rain · {day.wind_speed_max} km/h wind</small>
                <em className={`forecast-risk ${severityClass(day.severity)}`}>
                  {Math.round(day.score)} / 100
                </em>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
