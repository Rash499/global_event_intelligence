import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeEvent } from "../test/factories";
import EventList from "./EventList";

vi.mock("./EventCard", () => ({
  default: ({ event, index, variant }) => (
    <div data-testid="card" data-index={index} data-variant={variant}>{event.title}</div>
  ),
}));

describe("EventList", () => {
  it("shows the empty state when there are no events", () => {
    render(<EventList events={[]} />);
    expect(screen.getByText("No events found")).toBeInTheDocument();
  });

  it("shows skeletons instead of the empty state while loading", () => {
    render(<EventList events={[]} loading />);
    expect(screen.getByRole("status", { name: "Loading events" })).toBeInTheDocument();
    expect(screen.queryByText("No events found")).not.toBeInTheDocument();
  });

  it("prefers real data over skeletons even while refreshing", () => {
    render(<EventList events={[makeEvent()]} loading />);
    expect(screen.getAllByTestId("card")).toHaveLength(1);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("passes index (for stagger) and variant to each card", () => {
    render(
      <EventList
        events={[makeEvent({ id: 1, title: "A" }), makeEvent({ id: 2, title: "B" })]}
        variant="grid"
      />
    );
    const cards = screen.getAllByTestId("card");
    expect(cards.map((c) => c.dataset.index)).toEqual(["0", "1"]);
    expect(cards.every((c) => c.dataset.variant === "grid")).toBe(true);
  });
});
