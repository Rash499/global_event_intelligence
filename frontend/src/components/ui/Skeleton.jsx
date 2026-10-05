/** Shimmering placeholder block. Decorative, hidden from assistive tech. */
export function Skeleton({ className = "", style }) {
  return <span className={`skeleton ${className}`.trim()} style={style} aria-hidden="true" />;
}

export function EventCardSkeleton({ index = 0 }) {
  return (
    <div className="event-skeleton" style={{ "--i": index }} aria-hidden="true">
      <Skeleton className="event-skeleton-media" />
      <div className="event-skeleton-body">
        <Skeleton className="skeleton-line skeleton-line-short" />
        <Skeleton className="skeleton-line" />
        <Skeleton className="skeleton-line skeleton-line-mid" />
      </div>
    </div>
  );
}

export function EventListSkeleton({ count = 4 }) {
  return (
    <div className="event-list" role="status" aria-label="Loading events">
      {Array.from({ length: count }, (_, index) => (
        <EventCardSkeleton key={index} index={index} />
      ))}
    </div>
  );
}

/** Fallback while a lazily loaded screen downloads. */
export function ViewFallback({ label = "Loading view" }) {
  return (
    <div className="view-fallback" role="status" aria-label={label}>
      <Skeleton className="view-fallback-title" />
      <div className="view-fallback-grid">
        <Skeleton className="view-fallback-card" />
        <Skeleton className="view-fallback-card" />
        <Skeleton className="view-fallback-card" />
      </div>
    </div>
  );
}
