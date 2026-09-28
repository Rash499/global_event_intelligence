import { useEffect, useMemo, useState } from "react";
import DashboardPulse from "./DashboardPulse";
import GlobalDashboardFilters from "./GlobalDashboardFilters";
import GlobalDashboardHeader from "./GlobalDashboardHeader";
import GlobalEventResults from "./GlobalEventResults";
import { useGlobalEventFilters } from "./useGlobalEventFilters";
import { getGlobalStatistics } from "../../services/api.jsx";

export default function GlobalEventDashboard({ events }) {
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [overview, setOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const filters = useGlobalEventFilters(events);

  useEffect(() => {
    let active = true;

    const loadOverview = async () => {
      try {
        const data = await getGlobalStatistics();
        if (active) setOverview(data);
      } catch (error) {
        console.error("Failed to load global intelligence overview:", error);
      } finally {
        if (active) setOverviewLoading(false);
      }
    };

    loadOverview();

    return () => {
      active = false;
    };
  }, []);

  const timelineData = useMemo(() => {
    const items = overview?.timeline || [];

    return items.map((item) => ({
      label: item.date ? item.date.slice(5) : "—",
      value: item.count || 0,
      major: item.major_count || 0,
    }));
  }, [overview]);

  const categoryData = useMemo(() => {
    const items = overview?.category_breakdown || [];

    return items.slice(0, 6).map((item) => ({
      name: item.category ? item.category.replaceAll("_", " ") : "Other",
      count: item.count || 0,
      major: item.major_count || 0,
      avg: item.average_importance || 0,
    }));
  }, [overview]);

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

          <div className="analytics-grid">
            <div className="analytics-panel">
              <div className="panel-header analytics-header">
                <div>
                  <p className="eyebrow">INTELLIGENCE TIMELINE</p>
                  <h3>Activity trend</h3>
                </div>
              </div>

              {overviewLoading ? (
                <div className="analytics-placeholder">Loading intelligence overview...</div>
              ) : (
                <div className="timeline-chart" aria-label="Event timeline chart">
                  {timelineData.length ? (
                    timelineData.map((point) => (
                      <div key={point.label} className="timeline-point" title={`${point.value} events`}>
                        <span className="timeline-bar" style={{ height: `${Math.max(14, point.value * 18)}px` }} />
                        <small>{point.label}</small>
                      </div>
                    ))
                  ) : (
                    <div className="analytics-placeholder">No recent trend data available.</div>
                  )}
                </div>
              )}
            </div>

            <div className="analytics-panel">
              <div className="panel-header analytics-header">
                <div>
                  <p className="eyebrow">CATEGORY INTELLIGENCE</p>
                  <h3>Top themes</h3>
                </div>
              </div>

              <div className="category-breakdown" aria-label="Category breakdown">
                {categoryData.length ? (
                  categoryData.map((item) => (
                    <div key={item.name} className="category-row">
                      <div className="category-row-topline">
                        <span>{item.name}</span>
                        <strong>{item.count}</strong>
                      </div>
                      <div className="category-bar-track">
                        <span style={{ width: `${Math.min(100, (item.count / Math.max(1, categoryData[0].count)) * 100)}%` }} />
                      </div>
                      <small>{item.major} major · avg {item.avg.toFixed(1)}</small>
                    </div>
                  ))
                ) : (
                  <div className="analytics-placeholder">No category data yet.</div>
                )}
              </div>
            </div>
          </div>

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
