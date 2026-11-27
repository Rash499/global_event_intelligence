import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/api.jsx", () => ({
  getCountriesSummary: vi.fn(async () => ({
    count: 1,
    items: [
      {
        country_code: "JP",
        country: "Japan",
        event_count: 3,
        max_severity: 9.1,
        average_severity: 7.0,
        developing: 1,
        trend: { events_24h: 2, events_7d: 3, events_previous_7d: 1, direction: "rising" },
      },
    ],
  })),
  getCountryRisk: vi.fn(async () => ({
    country: "Japan",
    country_code: "JP",
    period_days: 30,
    total_events: 3,
    articles: 5,
    publishers: 2,
    coverage: { level: "partial", note: "5 articles from 2 publishers provide partial coverage." },
    dimensions: [
      {
        dimension: "natural_disasters",
        event_count: 2,
        average_severity: 8.0,
        max_severity: 9.1,
        developing_events: 1,
        categories: ["natural_disaster"],
        input_event_ids: [1, 2],
        coverage: "observed",
      },
      {
        dimension: "conflict_security",
        event_count: 0,
        average_severity: null,
        max_severity: null,
        developing_events: 0,
        categories: ["armed_conflict"],
        input_event_ids: [],
        coverage: "no_events",
      },
    ],
    movement: { events_24h: 2, events_previous_24h: 1, events_7d: 3, events_previous_7d: 1 },
    active_signals: [
      { category: "natural_disaster", label: "Natural Disasters", event_count: 2, max_severity: 9.1, latest_at: "2026-11-27T03:00:00Z" },
    ],
    timeline: {
      window_days: 7,
      days: [
        { date: "2026-11-21", total: 0, max_severity: null, by_category: {} },
        { date: "2026-11-22", total: 0, max_severity: null, by_category: {} },
        { date: "2026-11-23", total: 0, max_severity: null, by_category: {} },
        { date: "2026-11-24", total: 0, max_severity: null, by_category: {} },
        { date: "2026-11-25", total: 0, max_severity: null, by_category: {} },
        { date: "2026-11-26", total: 1, max_severity: 6.4, by_category: { natural_disaster: { events: 1, max_severity: 6.4 } } },
        { date: "2026-11-27", total: 2, max_severity: 9.1, by_category: { natural_disaster: { events: 2, max_severity: 9.1 } } },
      ],
    },
    recent_events: [
      { id: 1, title: "Magnitude 7.2 earthquake strikes Japan", severity: 9.1, event_state: "ongoing" },
    ],
    methodology: "Indicators are counts and severity averages of stored events.",
    limitations: ["Countries with less collected reporting will show fewer events."],
  })),
}));

const { default: CountriesView } = await import("./CountriesView.jsx");

describe("CountriesView (PR-3)", () => {
  it("shows trend, movement, active signals and the 7-day lane timeline", async () => {
    render(<CountriesView initialSelection="JP" />);

    // List trend column: rising, 3 events in 7d vs 1 in the previous 7d.
    await waitFor(() => expect(screen.getByText(/▲/)).toBeInTheDocument());

    // Movement stats + the honest framing of what movement means.
    await waitFor(() => expect(screen.getByText("Events · 24h")).toBeInTheDocument());
    expect(screen.getByText(/Movement compares stored reporting volume/)).toBeInTheDocument();

    // Active-signal chips carry count and worst severity.
    expect(screen.getByText("Active signals")).toBeInTheDocument();
    expect(screen.getByText(/Natural Disasters · 2 events · max 9\.1/)).toBeInTheDocument();
    expect(screen.getByText(/A missing signal means nothing was collected/)).toBeInTheDocument();

    // Lane timeline: Natural & weather lane, 2026-11-27 cell with 2 events.
    expect(screen.getByText("7-day activity")).toBeInTheDocument();
    expect(
      screen.getByTitle(/Natural & weather · 2026-11-27: 2 stored events, max severity 9\.1/)
    ).toBeInTheDocument();
    expect(
      screen.getByTitle(/Natural & weather · 2026-11-21: nothing collected/)
    ).toBeInTheDocument();
  });
});
