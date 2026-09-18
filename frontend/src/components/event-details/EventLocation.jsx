export default function EventLocation({ details }) {
  const hasCoordinates =
    details.latitude !== null &&
    details.latitude !== undefined &&
    details.longitude !== null &&
    details.longitude !== undefined;

  if (!hasCoordinates) return null;

  return (
    <div className="coordinates">
      <div>
        <span>Event location</span>
        <strong>
          {Number(details.latitude).toFixed(4)}, {Number(details.longitude).toFixed(4)}
        </strong>
      </div>
      <a
        href={`https://www.google.com/maps?q=${details.latitude},${details.longitude}`}
        target="_blank"
        rel="noopener noreferrer"
      >
        Open map <span aria-hidden="true">↗</span>
      </a>
    </div>
  );
}
