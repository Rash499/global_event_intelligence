import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { daysAgo, makeEvent } from "../test/factories";
import StatsBar from "./StatsBar";

const card = (label) => screen.getByText(label).closest(".stat-card");

describe("StatsBar", () => {
  it("counts only the last seven days", () => {
    render(
      <StatsBar
        events={[
          makeEvent({ id: 1 }),
          makeEvent({ id: 2, event_time: daysAgo(3) }),
          makeEvent({ id: 3, event_time: daysAgo(10) }),
        ]}
      />
    );
    expect(within(card("Events last 7 days")).getByText("2")).toBeInTheDocument();
  });

  it("counts major events (importance 8+), countries and categories", () => {
    render(
      <StatsBar
        events={[
          makeEvent({ id: 1, importance: 8, country_code: "JP", category: "conflict" }),
          makeEvent({ id: 2, importance: 7, country_code: "JP", category: "economy" }),
          makeEvent({ id: 3, importance: 10, country_code: "FR", category: "conflict" }),
        ]}
      />
    );
    expect(within(card("Major events last 7 days")).getByText("2")).toBeInTheDocument();
    expect(within(card("Countries last 7 days")).getByText("2")).toBeInTheDocument();
    expect(within(card("Categories last 7 days")).getByText("2")).toBeInTheDocument();
  });

  it("ignores events without a valid date and shows zeros when empty", () => {
    render(<StatsBar events={[makeEvent({ event_time: "not-a-date" }), makeEvent({ id: 2, event_time: undefined })]} />);
    expect(within(card("Events last 7 days")).getByText("0")).toBeInTheDocument();
  });

  it("ignores future-dated events", () => {
    const future = new Date(Date.now() + 86_400_000).toISOString();
    render(<StatsBar events={[makeEvent({ event_time: future })]} />);
    expect(within(card("Events last 7 days")).getByText("0")).toBeInTheDocument();
  });

  it("staggers the four cards", () => {
    const { container } = render(<StatsBar events={[]} />);
    const cards = [...container.querySelectorAll(".stat-card")];
    expect(cards.map((c) => c.style.getPropertyValue("--i"))).toEqual(["0", "1", "2", "3"]);
  });

  it("is labelled as a region", () => {
    render(<StatsBar events={[]} />);
    expect(screen.getByLabelText("Global event summary")).toBeInTheDocument();
  });
});
