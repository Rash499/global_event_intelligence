import { useEffect, useState } from "react";

import { formatRelativeTime } from "../services/dateFormat.jsx";
import EventComments from "./interactions/EventComments";
import EventInteractionBar from "./interactions/EventInteractionBar";
import { useEventInteractions } from "./interactions/InteractionProvider";
import { getEventImage } from "../services/api.jsx";

const severityIcons = {
  critical: "!",
  high: "▲",
  moderate: "◆",
  low: "•",
};

const impactLabels = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  low: "Low",
};

const getSeverity = (importance) => {
  if (importance >= 8) return "critical";
  if (importance >= 6) return "high";
  if (importance >= 4) return "moderate";
  return "low";
};

export const formatCategory = (category) =>
  category ? category.replaceAll("_", " ") : "Uncategorized";

export default function EventCard({ event, variant = "grid", onSelect }) {
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [imageUrl, setImageUrl] = useState(event.image_url || "");
  const { syncEvent } = useEventInteractions();

  useEffect(() => {
    setImageUrl(event.image_url || "");
    setImageFailed(false);

    if (variant !== "grid" || event.image_url) return undefined;

    let active = true;
    getEventImage(event.id)
      .then((data) => {
        if (active && data.image_url) setImageUrl(data.image_url);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [event.id, event.image_url, variant]);

  useEffect(() => {
    syncEvent(event);
  }, [
    event,
    event.id,
    event.like_count,
    event.comment_count,
    event.liked,
    syncEvent,
  ]);

  const severity = getSeverity(event.importance);
  const showImage = Boolean(imageUrl) && !imageFailed;
  const eventTime = formatRelativeTime(event.event_time);

  const fullEventTime = event.event_time
    ? new Date(event.event_time).toLocaleString(undefined, {
        dateStyle: "full",
        timeStyle: "short",
      })
    : "Unknown time";

  const confidenceValue = Number(event.confidence);
  const confidenceLabel = Number.isFinite(confidenceValue)
    ? `${Math.round(
        confidenceValue > 1 ? confidenceValue : confidenceValue * 100
      )}%`
    : "—";

  const latitude = Number(event.latitude);
  const longitude = Number(event.longitude);
  const coordinatesLabel =
    Number.isFinite(latitude) && Number.isFinite(longitude)
      ? `${latitude.toFixed(2)}, ${longitude.toFixed(2)}`
      : null;

  const openDetails = () => onSelect?.(event);

  const stopInteraction = (pointerEvent) => {
    pointerEvent.stopPropagation();
  };

  return (
    <article
      className={`event-card event-card-${variant} event-card-${severity}`}
    >
      <button
        type="button"
        className="event-card-select"
        onClick={openDetails}
        aria-label={`Open details for ${event.title || "untitled event"}`}
      >
        <span className="event-card-media">
          {showImage ? (
            <img
              src={imageUrl}
              alt=""
              loading="lazy"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <span className="event-card-placeholder" aria-hidden="true">
              <span className="event-card-placeholder-glyph">
                {severityIcons[severity]}
              </span>
              <span className="event-card-placeholder-label">
                {formatCategory(event.category)}
              </span>
            </span>
          )}

          <span className="event-card-media-badge">
            {event.importance ?? "-"}
            <small>/10</small>
          </span>
        </span>

        <span className="event-card-body">
          <span className="event-card-badges">
            <span className={`severity severity-${severity}`}>
              {impactLabels[severity]} impact
            </span>
            <span className="event-card-category">
              {formatCategory(event.category)}
            </span>
          </span>

          <span className="event-card-title">
            {event.title || "Untitled event"}
          </span>

          <span className="event-card-meta">
            <span>{event.country || "Global"}</span>
            <span aria-hidden="true">•</span>
            <span>{eventTime}</span>
          </span>

          <span className="event-card-summary">
            {event.summary || "No summary available for this event yet."}
          </span>
        </span>
      </button>

      <div
        className="event-card-details"
        onClick={stopInteraction}
        onKeyDown={stopInteraction}
      >
        <button
          type="button"
          className="event-card-details-toggle"
          aria-expanded={detailsOpen}
          onClick={() => setDetailsOpen((open) => !open)}
        >
          <span>
            {detailsOpen ? "Hide event details" : "Show event details"}
          </span>
          <span aria-hidden="true">{detailsOpen ? "▴" : "▾"}</span>
        </button>

        {detailsOpen && (
          <div className="event-card-details-panel">
            <p className="event-card-description">
              {event.description ||
                event.summary ||
                "No detailed description available for this event yet."}
            </p>

            <dl className="event-card-facts">
              <div>
                <dt>Confidence</dt>
                <dd>{confidenceLabel}</dd>
              </div>
              <div>
                <dt>Importance</dt>
                <dd>{event.importance ?? "—"} / 10</dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{formatCategory(event.category)}</dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{event.country || "Global"}</dd>
              </div>
              {coordinatesLabel && (
                <div>
                  <dt>Coordinates</dt>
                  <dd>{coordinatesLabel}</dd>
                </div>
              )}
              <div>
                <dt>Event time</dt>
                <dd>{fullEventTime}</dd>
              </div>
            </dl>
          </div>
        )}
      </div>

      <footer
        className="event-card-footer"
        onClick={stopInteraction}
        onKeyDown={stopInteraction}
      >
        <EventInteractionBar
          event={event}
          showComments={commentsOpen}
          onToggleComments={() => setCommentsOpen((open) => !open)}
        />
      </footer>

      {commentsOpen && (
        <div onClick={stopInteraction} onKeyDown={stopInteraction}>
          <EventComments event={event} />
        </div>
      )}
    </article>
  );
}
