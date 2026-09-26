import { useEffect } from "react";

export default function AlertToast({ message, onDismiss }) {
  useEffect(() => {
    if (!message) return undefined;

    const timeoutId = window.setTimeout(onDismiss, 8000);
    return () => window.clearTimeout(timeoutId);
  }, [message, onDismiss]);

  if (!message) return null;

  return (
    <div className="event-alert" role="alert" aria-live="assertive">
      <span className="event-alert-indicator" aria-hidden="true" />
      <span>{message}</span>
      <button type="button" aria-label="Dismiss new events alert" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
}