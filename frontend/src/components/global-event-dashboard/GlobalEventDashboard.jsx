import { useState } from "react";
import DashboardPulse from "./DashboardPulse";
import GlobalDashboardFilters from "./GlobalDashboardFilters";
import GlobalDashboardHeader from "./GlobalDashboardHeader";
import GlobalEventResults from "./GlobalEventResults";
import { useGlobalEventFilters } from "./useGlobalEventFilters";

export default function GlobalEventDashboard({ events }) {
  const [selectedEvent, setSelectedEvent] = useState(null);
  const filters = useGlobalEventFilters(events);

  return (
    <section className="global-dashboard">
      {selectedEvent ? (
        <GlobalEventResults
          events={filters.filteredEvents}
          selectedEvent={selectedEvent}
          onSelect={setSelectedEvent}
          onBack={() => setSelectedEvent(null)}
        />
      ) : (
        <>
          <GlobalDashboardHeader
            eventCount={filters.filteredEvents.length}
            hasActiveFilters={filters.hasActiveFilters}
          />
          <DashboardPulse
            summary={filters.summary}
            total={filters.filteredEvents.length}
          />
          <GlobalDashboardFilters
            category={filters.category}
            onCategoryChange={filters.setCategory}
            categories={filters.categories}
            country={filters.country}
            onCountryChange={filters.setCountry}
            countries={filters.countries}
            minImportance={filters.minImportance}
            onImportanceChange={filters.setMinImportance}
            hasActiveFilters={filters.hasActiveFilters}
            onReset={filters.resetFilters}
          />
          <GlobalEventResults
            events={filters.filteredEvents}
            selectedEvent={null}
            onSelect={setSelectedEvent}
            onBack={() => setSelectedEvent(null)}
          />
        </>
      )}
    </section>
  );
}
