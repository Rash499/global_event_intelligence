export default function WeatherModeToggle({ mode, onChange }) {
  return (
    <div className="mode-toggle" aria-label="Map mode">
      <button
        type="button"
        className={mode === "events" ? "active" : ""}
        onClick={() => onChange("events")}
      >
        📰 Events
      </button>
      <button
        type="button"
        className={mode === "weather" ? "active weather-active" : ""}
        onClick={() => onChange("weather")}
      >
        🌤 Weather
      </button>
    </div>
  );
}
