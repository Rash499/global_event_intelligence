const SQLITE_TIMESTAMP = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;

const parseDate = (value) => {
  if (!value) return null;

  // SQLite stores "YYYY-MM-DD HH:MM:SS" in UTC without a timezone marker.
  const normalized = SQLITE_TIMESTAMP.test(value)
    ? `${value.replace(" ", "T")}Z`
    : value;

  const date = new Date(normalized);

  return Number.isNaN(date.getTime()) ? null : date;
};

export const formatDateTime = (value, fallback = "Unknown time") => {
  const date = parseDate(value);

  if (!date) return fallback;

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
};

export const formatRelativeTime = (value, fallback = "Unknown time") => {
  const date = parseDate(value);

  if (!date) return fallback;

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  if (days <= 7) return `${days}d ago`;

  return formatDateTime(value, fallback);
};
