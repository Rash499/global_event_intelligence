import { useEffect, useState } from "react";
import { getEvent } from "../services/api.jsx";

export default function EventDetails({
  event,
  onBack,
}) {
  const [details, setDetails] = useState(event);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadDetails = async () => {
      try {
        const data = await getEvent(event.id);

        if (active) {
          setDetails(data);
        }
      } catch (error) {
        console.error("Failed to load event details:", error);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadDetails();

    return () => {
      active = false;
    };
  }, [event.id]);

  return (
    <article className="detail-panel">
      <button
        className="back-button"
        onClick={onBack}
      >
        ← Back to events
      </button>

      <span className="badge">
        {details.category?.replace("_", " ")}
      </span>

      <h2>{details.title}</h2>

      <p className="detail-summary">
        {details.summary}
      </p>

      <div className="detail-grid">
        <div>
          <span>Country</span>
          <strong>
            {details.country || "Global"}
          </strong>
        </div>

        <div>
          <span>Importance</span>
          <strong>
            {details.importance}/10
          </strong>
        </div>

        <div>
          <span>Confidence</span>
          <strong>
            {Math.round(
              details.confidence * 100
            )}
            %
          </strong>
        </div>

        <div>
          <span>Date</span>
          <strong>
            {details.event_time
              ? new Date(
                  details.event_time
                ).toLocaleDateString()
              : "Unknown"}
          </strong>
        </div>
      </div>

      {details.latitude !== null &&
        details.longitude !== null && (
          <div className="coordinates">
            <span>Location</span>

            <strong>
              {details.latitude.toFixed(4)},{" "}
              {details.longitude.toFixed(4)}
            </strong>
          </div>
        )}

      <div className="sources-section">
        <h3>News Sources</h3>

        {loading ? (
          <p>Loading sources...</p>
        ) : details.sources?.length ? (
          <div className="sources-list">
            {details.sources.map(
              (source, index) => (
                <a
                  key={index}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <strong>
                    {source.title}
                  </strong>

                  <small>
                    {source.source}
                  </small>
                </a>
              )
            )}
          </div>
        ) : (
          <p>No source information available.</p>
        )}
      </div>
    </article>
  );
}