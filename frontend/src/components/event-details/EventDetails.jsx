import { useEffect, useState } from "react";
import { getEvent } from "../../services/api.jsx";
import { getLocalUserId } from "../../services/eventIdentity.jsx";
import EventComments from "../interactions/EventComments";
import EventInteractionBar from "../interactions/EventInteractionBar";
import EventHeader from "./EventHeader";
import EventLocation from "./EventLocation";
import EventMetrics from "./EventMetrics";
import EventSources from "./EventSources";

export default function EventDetails({ event, onBack }) {
  const [details, setDetails] = useState(event);
  const [commentsOpen, setCommentsOpen] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadDetails = async () => {
      try {
        const data = await getEvent(event.id, getLocalUserId());

        if (active) {
          setDetails((previous) => ({ ...previous, ...data }));
        }
      } catch (error) {
        console.error("Failed to load event details:", error);
      } finally {
        if (active) setLoading(false);
      }
    };

    loadDetails();

    return () => {
      active = false;
    };
  }, [event.id]);

  const sources = details.sources || [];

  return (
    <article className="detail-panel">
      <EventHeader details={details} loading={loading} onBack={onBack} />
      <EventMetrics details={details} sourceCount={sources.length} />
      <EventLocation details={details} />

      <section className="detail-engagement" aria-label="Event engagement">
        <EventInteractionBar
          event={details}
          showComments={commentsOpen}
          onToggleComments={() => setCommentsOpen((open) => !open)}
        />
        {commentsOpen && <EventComments event={details} />}
      </section>

      <EventSources sources={sources} loading={loading} />
    </article>
  );
}
