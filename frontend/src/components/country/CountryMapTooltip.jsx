import { clamp, shortLabel, VIEW_W, VIEW_H } from "./countryMapProjection.jsx";

export default function CountryMapTooltip({ hoveredPin }) {
  if (!hoveredPin) return null;

  const tooltipText = shortLabel(hoveredPin.event?.title, 34);
  const tooltipWidth = clamp(tooltipText.length * 6.4 + 28, 150, 300);

  return (
    <g
      className="country-map-tip"
      transform={`translate(${clamp(
        hoveredPin.x,
        tooltipWidth / 2 + 6,
        VIEW_W - tooltipWidth / 2 - 6
      )} ${clamp(hoveredPin.y - 32, 24, VIEW_H - 10)})`}
      aria-hidden="true"
    >
      <rect x={-tooltipWidth / 2} y="-19" width={tooltipWidth} height="36" rx="8" />
      <text textAnchor="middle" y="-5">
        {tooltipText}
      </text>
      <text className="country-map-tip-meta" textAnchor="middle" y="8">
        {String(hoveredPin.event?.category || "unclassified").replaceAll("_", " ")} ·{" "}
        {hoveredPin.event?.importance ?? "—"}/10
      </text>
    </g>
  );
}
