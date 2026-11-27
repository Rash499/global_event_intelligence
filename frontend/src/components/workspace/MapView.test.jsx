import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const globeProps = vi.fn();

vi.mock("../../services/api.jsx", () => ({
  getMapEvents: vi.fn(async (params) => {
    if (params.major_only) {
      return {
        items: [],
        country_shading: [],
        coverage: { plotted_with_coordinates: 0, country_level_only: 0, no_location: 0 },
        major_definition: "severity >= 6.5 (high/critical) or importance >= 8",
        legend: { note: "test" },
      };
    }
    // Fallback (all events): one country-precision event, no coordinates.
    return {
      items: [
        {
          id: 7,
          title: "Flooding displaces thousands in Sri Lanka",
          country: "Sri Lanka",
          country_code: "LK",
          latitude: null,
          longitude: null,
          location_precision: "country",
          severity: 6.4,
          importance: 6,
          occurred_at: new Date().toISOString(),
        },
        {
          id: 8,
          title: "Magnitude 7.2 earthquake near Tokyo",
          country: "Japan",
          country_code: "JP",
          latitude: 35.6762,
          longitude: 139.6503,
          location_precision: "approximate",
          severity: 9.1,
          importance: 9,
          occurred_at: new Date().toISOString(),
        },
      ],
      country_shading: [{ country_code: "LK", country: "Sri Lanka", events: 1, max_severity: 6.4, latitude: 7.87, longitude: 80.77, is_country_aggregate: true }],
      // (second item added below in items)
      coverage: { plotted_with_coordinates: 0, country_level_only: 1, no_location: 0 },
      legend: { note: "test" },
    };
  }),
}));

vi.mock("../Globe.jsx", () => ({
  default: (props) => {
    globeProps(props);
    return <div data-testid="globe" />;
  },
}));

vi.mock("../globe/FlatMap.jsx", () => ({
  default: (props) => {
    globeProps(props);
    return <div data-testid="flat-map" />;
  },
}));

const { default: MapView } = await import("./MapView.jsx");
const { getMapEvents } = await import("../../services/api.jsx");

describe("MapView", () => {
  it("falls back to all events when no major events exist, and shades country-level events", async () => {
    render(<MapView mode="events" />);

    // The user is told why the scope changed instead of seeing a blank map.
    await waitFor(() =>
      expect(screen.getByText(/showing all events in that window instead/i)).toBeInTheDocument()
    );

    // The country-precision event reaches the globe as shading data even
    // though it can never be a pin.
    const lastProps = globeProps.mock.calls.at(-1)[0];
    // The "near Tokyo" event has coordinates at approximate precision: it
    // must become a pin (a stale whitelist used to drop it silently).
    expect(lastProps.events.filter((e) => !e.is_country_aggregate)).toHaveLength(1);
    expect(lastProps.events.find((e) => !e.is_country_aggregate).location_precision).toBe("approximate");
    // Plus the Sri Lanka country aggregate bubble (labelled, not a pin).
    const aggregate = lastProps.events.find((e) => e.is_country_aggregate);
    expect(aggregate.country_code).toBe("LK");
    expect(aggregate.aggregate_count).toBe(1);
    expect(lastProps.polygonEvents).toHaveLength(2);
    expect(lastProps.polygonEvents[0].country_code).toBe("LK");

    expect(screen.getByText(/Flooding displaces thousands/)).toBeInTheDocument();
  });

  it("offers registry layers and sends the selection as a categories filter", async () => {
    getMapEvents.mockClear();
    render(<MapView mode="events" />);
    await waitFor(() =>
      expect(screen.getByText(/showing all events in that window instead/i)).toBeInTheDocument()
    );

    // All seven registry layers are offered, plus the clustering toggle.
    expect(screen.getByText("Map layers")).toBeInTheDocument();
    expect(screen.getByLabelText(/Cluster nearby pins/)).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: /Politics & unrest/ }));

    // The refetch excludes the politics/unrest categories but keeps the rest.
    await waitFor(() => {
      const withCategories = getMapEvents.mock.calls
        .map(([params]) => params)
        .filter((params) => typeof params.categories === "string");
      expect(withCategories.length).toBeGreaterThan(0);
      const latest = withCategories.at(-1).categories;
      expect(latest).not.toContain("political_development");
      expect(latest).not.toContain("protest_unrest");
      expect(latest).toContain("natural_disaster");
    });
    expect(screen.getByRole("button", { name: /Politics & unrest/ })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
  });

  it("switches between globe and flat map surfaces with the same data", async () => {
    render(<MapView mode="events" />);
    await waitFor(() =>
      expect(screen.getByText(/showing all events in that window instead/i)).toBeInTheDocument()
    );
    expect(screen.getByTestId("globe")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Flat map" }));
    expect(screen.getByTestId("flat-map")).toBeInTheDocument();
    expect(screen.queryByTestId("globe")).not.toBeInTheDocument();
    // The flat surface receives the same points (pin + country aggregate).
    const flatProps = globeProps.mock.calls.at(-1)[0];
    expect(flatProps.events).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Globe" }));
    expect(screen.getByTestId("globe")).toBeInTheDocument();
  });

  it("time replay hides events that had not occurred yet at the replay point", async () => {
    render(<MapView mode="events" />);
    await waitFor(() =>
      expect(screen.getByText(/showing all events in that window instead/i)).toBeInTheDocument()
    );
    // Both fixture events occurred "now"; replaying to the start of the
    // 7-day window must hide both pins and the aggregate, and say so.
    fireEvent.change(screen.getByLabelText(/Time replay position/), {
      target: { value: "0" },
    });
    await waitFor(() =>
      expect(screen.getByText(/Time replay: showing 0 events/)).toBeInTheDocument()
    );
    const lastProps = globeProps.mock.calls.at(-1)[0];
    expect(lastProps.events).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Back to live" }));
    await waitFor(() => {
      const props = globeProps.mock.calls.at(-1)[0];
      expect(props.events).toHaveLength(2);
    });
  });
});
