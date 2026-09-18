export const formatCategory = (category) =>
  category ? category.replaceAll("_", " ") : "Uncategorized";

export const formatDate = (date) => {
  if (!date) return "Unknown time";

  return new Date(date).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
};

export const getConfidence = (confidence) =>
  `${Math.round((Number(confidence) || 0) * 100)}%`;

export const getImportanceLabel = (importance) => {
  if (importance >= 8) return "Critical";
  if (importance >= 6) return "High";
  if (importance >= 4) return "Moderate";
  return "Low";
};
