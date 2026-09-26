import { useEffect, useState } from "react";

import { formatRelativeTime } from "../services/dateFormat.jsx";
import EventComments from "./interactions/EventComments";
import EventInteractionBar from "./interactions/EventInteractionBar";
import { useEventInteractions } from "./interactions/InteractionProvider";

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
  const [imageFailed, setImageFailed] = useState(false);
  const { syncEvent } = useEventInteractions();

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
  const showImage = Boolean(event.image_url) && !imageFailed;
  const eventTime = formatRelativeTime(event.event_time);

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
              src={event.image_url}
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
