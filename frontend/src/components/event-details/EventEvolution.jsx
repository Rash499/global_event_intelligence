import { useEffect, useState } from "react";
import { getEventTimeline } from "../../services/api.jsx";

export default function EventEvolution({ eventId }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getEventTimeline(eventId)
      .then((data) => { if (active) setHistory(data); })
      .catch((err) => { console.error(err); if (active) setError("Historical evidence is unavailable."); });
    return () => { active = false; };
  }, [eventId]);

  if (error) return <section className="event-evolution"><div className="event-evolution-header"><h3>Event Evolution</h3></div><p>{error}</p></section>;
  if (!history) return <section className="event-evolution"><div className="event-evolution-header"><h3>Event Evolution</h3></div><p>Loading historical evidence...</p></section>;

  return (
    <section className="event-evolution" aria-label="Event evolution">
      <div className="event-evolution-header">
        <div><span className="section-eyebrow">Evolution</span><h3>Event Timeline</h3></div>
        <span>{history.source_diversity.unique_domains} domains · {history.source_diversity.total_articles} articles</span>
      </div>
      {history.momentum && <div className={"event-momentum " + history.momentum.state}><strong>Reporting activity: {history.momentum.state.replaceAll("_", " ")}</strong><span>{history.momentum.message}</span></div>}
      {history.conflicting_reports && <div className="event-conflict">⚠ Conflicting evidence detected. Values are preserved by source rather than selecting a winner.</div>}
      <div className="event-timeline">
        {history.timeline.map((item) => (
          <article key={item.article_id} className="event-timeline-entry">
            <div className="event-timeline-dot" />
            <div>
              <time>{item.timestamp ? new Date(item.timestamp).toLocaleString() : "Timestamp unavailable"}</time>
              <strong>{item.title}</strong>
              <span>{item.source} · {item.category}</span>
              {item.summary && <p>{item.summary}</p>}
              {item.changes?.map((change, index) => (
                <em key={item.article_id + "-" + index}>{change.type.replaceAll("_", " ")}</em>
              ))}
            </div>
          </article>
        ))}
      </div>
      {history.claims.length > 0 && (
        <div className="event-claims">
          <h4>Claims & evidence</h4>
          {history.claims.map((claim, index) => (
            <div key={claim.article_id + "-" + index}><strong>{claim.value}</strong><span>{claim.claim_type} · {claim.source || "unknown source"} · {claim.timestamp || "unknown time"}</span></div>
          ))}
        </div>
      )}
    </section>
  );
}
