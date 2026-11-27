import { render, screen, waitFor } from "@testing-library/react";
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
        },
      ],
      country_shading: [{ country_code: "LK", country: "Sri Lanka", events: 1, max_severity: 6.4 }],
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

const { default: MapView } = await import("./MapView.jsx");

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
    expect(lastProps.events).toHaveLength(0);
    expect(lastProps.polygonEvents).toHaveLength(1);
    expect(lastProps.polygonEvents[0].country_code).toBe("LK");

    expect(screen.getByText(/Flooding displaces thousands/)).toBeInTheDocument();
  });
});
