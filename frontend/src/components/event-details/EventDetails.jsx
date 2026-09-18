import { useEffect, useState } from "react";
import { getEvent } from "../../services/api.jsx";
import EventHeader from "./EventHeader";
import EventLocation from "./EventLocation";
import EventMetrics from "./EventMetrics";
import EventSources from "./EventSources";

export default function EventDetails({ event, onBack }) {
  const [details, setDetails] = useState(event);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadDetails = async () => {
      try {
        const data = await getEvent(event.id);

        if (active) setDetails(data);
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
      <EventSources sources={sources} loading={loading} />
    </article>
  );
}
