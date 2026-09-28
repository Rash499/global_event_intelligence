import { shortLabel } from "./countryMapProjection.jsx";

export default function CountryMapPins({
  pins,
  activeEventId,
  hoveredId,
  onSelect,
  onHover,
}) {
  return (
    <>
      {pins.map((pin) => {
        const isActive = activeEventId !== null && String(activeEventId) === pin.id;
        const isHovered = hoveredId === pin.id;

        return (
          <g
            key={pin.id}
            className={`country-map-pin ${isActive ? "is-active" : ""} ${
              isHovered ? "is-hover" : ""
            } ${pin.onMap ? "" : "is-off-view"}`}
            transform={`translate(${pin.x} ${pin.y})`}
            role="button"
            tabIndex={0}
            aria-label={`${shortLabel(pin.event?.title, 60)} — ${pin.level} importance`}
            onClick={(pointerEvent) => {
              pointerEvent.stopPropagation();
              onSelect?.(pin.event);
            }}
            onKeyDown={(keyEvent) => {
              if (keyEvent.key !== "Enter" && keyEvent.key !== " ") return;
              keyEvent.preventDefault();
              onSelect?.(pin.event);
            }}
            onMouseEnter={() => onHover(pin.id)}
            onFocus={() => onHover(pin.id)}
            onMouseLeave={() =>
              onHover((current) => (current === pin.id ? null : current))
            }
            onBlur={() => onHover((current) => (current === pin.id ? null : current))}
          >
            <title>{shortLabel(pin.event?.title, 80)}</title>
            {isActive ? (
              <circle className="country-map-pin-pulse" r="7" style={{ color: pin.color }} />
            ) : null}
            <circle
              className="country-map-pin-halo"
              r={isActive || isHovered ? 12 : 8.5}
              fill={pin.color}
            />
            <circle
              className="country-map-pin-core"
              r={isActive || isHovered ? 4.4 : 3.2}
              fill={pin.color}
            />
          </g>
        );
      })}
    </>
  );
}
