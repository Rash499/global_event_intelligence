import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/api.jsx", () => ({
  getDashboardOverview: vi.fn(async () => ({
    totals: {},
    severity_distribution: [],
    countries: [],
    source_mix: [],
    important_events: [],
    coverage: {},
    freshness: {},
    event_states: [],
  })),
  getAnomalies: vi.fn(async () => ({ items: [], count: 0 })),
  getConvergence: vi.fn(async () => ({
    window_days: 7,
    min_groups: 3,
    definition: "A category group counts as escalating for a country when...",
    count: 1,
    items: [
      {
        country_code: "JP",
        country: "Japan",
        escalated_groups: 3,
        total_current: 6,
        total_previous: 1,
        max_severity: 7.5,
        groups: [
          {
            group: "conflict_security",
            label: "Conflict & security",
            current: 2,
            previous: 1,
            max_severity: 7.0,
            escalated: true,
            reasons: ["volume_increase"],
            evidence: [{ id: 11, title: "Clash A", category: "armed_conflict", severity: 7.0, occurred_at: "2026-11-27T00:00:00Z" }],
          },
          {
            group: "natural_weather",
            label: "Natural & weather",
            current: 2,
            previous: 0,
            max_severity: 7.5,
            escalated: true,
            reasons: ["volume_increase"],
            evidence: [{ id: 12, title: "Quake A", category: "natural_disaster", severity: 7.5, occurred_at: "2026-11-27T00:00:00Z" }],
          },
          {
            group: "politics_unrest",
            label: "Politics & unrest",
            current: 2,
            previous: 0,
            max_severity: 5.5,
            escalated: true,
            reasons: ["volume_increase"],
            evidence: [],
          },
        ],
      },
    ],
  })),
}));

const { default: OverviewView } = await import("./OverviewView.jsx");

describe("OverviewView convergence panel", () => {
  it("lists converging countries with group chips and clickable evidence", async () => {
    const onSelectEvent = vi.fn();
    render(<OverviewView onSelectEvent={onSelectEvent} onNavigate={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Convergence")).toBeInTheDocument());
    expect(screen.getByText("Japan")).toBeInTheDocument();
    expect(screen.getByText(/3 groups escalating/)).toBeInTheDocument();
    expect(screen.getByText(/Conflict & security · 2 vs 1 · max 7\.0/)).toBeInTheDocument();
    expect(screen.getByText(/Natural & weather · 2 vs 0 · max 7\.5/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Quake A" }));
    expect(onSelectEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 12 }));
  });
});
