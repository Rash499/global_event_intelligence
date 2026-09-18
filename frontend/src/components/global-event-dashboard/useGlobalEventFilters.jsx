import { useMemo, useState } from "react";

export function useGlobalEventFilters(events) {
  const [category, setCategory] = useState("all");
  const [country, setCountry] = useState("all");
  const [minImportance, setMinImportance] = useState(1);

  const countries = useMemo(
    () => [
      "all",
      ...new Set(
        events.map((event) => event.country_code).filter(Boolean)
      ),
    ],
    [events]
  );

  const categories = useMemo(
    () => [
      "all",
      ...new Set(events.map((event) => event.category).filter(Boolean)),
    ],
    [events]
  );

  const filteredEvents = useMemo(
    () =>
      events.filter((event) => {
        const categoryMatch =
          category === "all" || event.category === category;
        const countryMatch = country === "all" || event.country_code === country;
        const importanceMatch = event.importance >= minImportance;

        return categoryMatch && countryMatch && importanceMatch;
      }),
    [events, category, country, minImportance]
  );

  const summary = useMemo(
    () => ({
      majorEvents: filteredEvents.filter((event) => event.importance >= 8)
        .length,
      countries: new Set(
        filteredEvents.map((event) => event.country_code).filter(Boolean)
      ).size,
      categories: new Set(
        filteredEvents.map((event) => event.category).filter(Boolean)
      ).size,
    }),
    [filteredEvents]
  );

  const hasActiveFilters =
    category !== "all" || country !== "all" || minImportance !== 1;

  const resetFilters = () => {
    setCategory("all");
    setCountry("all");
    setMinImportance(1);
  };

  return {
    category,
    setCategory,
    country,
    setCountry,
    minImportance,
    setMinImportance,
    countries,
    categories,
    filteredEvents,
    summary,
    hasActiveFilters,
    resetFilters,
  };
}
