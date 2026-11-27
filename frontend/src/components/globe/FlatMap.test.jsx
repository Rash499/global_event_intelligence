import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/worldGeoJson.jsx", () => ({
  loadWorldGeoJSON: vi.fn(async () => ({
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { ISO_A2: "JP", NAME: "Japan" },
        geometry: {
          type: "Polygon",
          coordinates: [[[129, 31], [146, 31], [146, 45], [129, 45], [129, 31]]],
        },
      },
    ],
  })),
}));

const { default: FlatMap } = await import("./FlatMap.jsx");

const pin = {
  id: 8,
  title: "Magnitude 7.2 earthquake near Tokyo",
  country: "Japan",
  latitude: 35.67,
  longitude: 139.65,
  importance: 9,
};

describe("FlatMap", () => {
  it("renders country paths and pins from the same payload as the globe", async () => {
    const onSelectEvent = vi.fn();
    const onSelectCountry = vi.fn();
    const { container } = render(
      <FlatMap
        mode="events"
        events={[pin]}
        polygonEvents={[{ ...pin, country_code: "JP" }]}
        onSelectEvent={onSelectEvent}
        onSelectCountry={onSelectCountry}
      />
    );

    const japanPath = await waitFor(() => {
      const path = container.querySelector("path.flatmap-country");
      expect(path).not.toBeNull();
      return path;
    });
    const titles = [...container.querySelectorAll("title")].map((node) => node.textContent);
    expect(titles).toContain("Japan");
    expect(titles.some((text) => text.includes("Magnitude 7.2 earthquake near Tokyo"))).toBe(true);

    fireEvent.click(container.querySelector("g.flatmap-point"));
    expect(onSelectEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 8 }));

    fireEvent.click(japanPath);
    expect(onSelectCountry).toHaveBeenCalledWith({ code: "JP", name: "Japan" });
  });

  it("zooms and resets via its controls", async () => {
    const { container } = render(<FlatMap mode="events" events={[]} polygonEvents={[]} />);
    await waitFor(() =>
      expect(container.querySelector("path.flatmap-country")).not.toBeNull()
    );

    const svg = screen.getByTestId("flat-map").querySelector("svg");
    const group = () => svg.querySelector("g").getAttribute("transform");
    expect(group()).toContain("scale(1)");

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(group()).toMatch(/scale\(1\.4\)/);

    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(group()).toContain("scale(1)");
  });
});
