export default function CountryMapControls({ zoom, onZoomChange, onReset }) {
  return (
    <div className="country-map-controls">
      <button
        type="button"
        className="country-map-btn"
        aria-label="Zoom in"
        disabled={zoom >= 6}
        onClick={() => onZoomChange(Math.min(6, Number((zoom + 0.5).toFixed(1))))}
      >
        +
      </button>
      <button
        type="button"
        className="country-map-btn"
        aria-label="Zoom out"
        disabled={zoom <= 1}
        onClick={() => onZoomChange(Math.max(1, Number((zoom - 0.5).toFixed(1))))}
      >
        −
      </button>
      <button
        type="button"
        className="country-map-btn country-map-btn-wide"
        onClick={onReset}
      >
        Reset
      </button>
      <span className="country-map-zoom-label">{zoom.toFixed(1)}×</span>
    </div>
  );
}
