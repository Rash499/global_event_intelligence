import { useEffect, useState } from "react";

import EventCard from "../EventCard";

const PAGE_SIZE = 18;

export default function EventHistoryGrid({ events, onSelect }) {
  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(events.length / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [events]);

  if (!events.length) {
    return (
      <div className="empty-state event-empty-state">
        <span className="empty-state-icon" aria-hidden="true">∅</span>
        <h3>No events found</h3>
        <p>Try another filter or collect the latest news to refresh the feed.</p>
      </div>
    );
  }

  const currentPage = Math.min(page, pageCount);
  const firstRow = (currentPage - 1) * PAGE_SIZE;
  const pageEvents = events.slice(firstRow, firstRow + PAGE_SIZE);
  const firstVisibleEvent = firstRow + 1;
  const lastVisibleEvent = Math.min(firstRow + PAGE_SIZE, events.length);

  return (
    <div>
      <div className="event-history-grid">
        {pageEvents.map((event) => (
          <EventCard
            key={event.id}
            event={event}
            variant="grid"
            onSelect={onSelect}
          />
        ))}
      </div>

      <nav className="event-pagination" aria-label="Event history pages">
        <span>
          Showing {firstVisibleEvent}-{lastVisibleEvent} of {events.length}
        </span>
        <div className="event-pagination-controls">
          <button
            type="button"
            onClick={() => setPage((current) => current - 1)}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          {Array.from({ length: pageCount }, (_, index) => index + 1).map(
            (pageNumber) => (
              <button
                type="button"
                className={pageNumber === currentPage ? "active" : ""}
                aria-current={pageNumber === currentPage ? "page" : undefined}
                onClick={() => setPage(pageNumber)}
                key={pageNumber}
              >
                {pageNumber}
              </button>
            )
          )}
          <button
            type="button"
            onClick={() => setPage((current) => current + 1)}
            disabled={currentPage === pageCount}
          >
            Next
          </button>
        </div>
      </nav>
    </div>
  );
}
