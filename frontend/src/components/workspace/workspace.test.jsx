import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/api.jsx", () => ({
  unifiedSearch: vi.fn(async (query) => ({
    query,
    events: [{ id: 11, title: "Ceasefire talks resume", category: "political_development", country_code: "SY", severity: 6.2 }],
    entities: [{ id: 3, name: "United Nations", entity_type: "organization", mention_count: 12 }],
    countries: [{ country_code: "SY", country: "Syria" }],
    articles: [],
  })),
}));

const { default: CommandPalette } = await import("./CommandPalette");
const { ConfidenceExplanation } = await import("./EventInvestigation.jsx");
const { default: EventRow } = await import("./EventRow");
const { Stat, Panel } = await import("./primitives.jsx");

const event = {
  id: 1,
  title: "Magnitude 7.1 earthquake offshore Japan",
  category: "natural_disaster",
  country: "Japan",
  severity: 9.2,
  severity_label: "critical",
  confidence: 0.81,
  priority_label: "flash",
  priority_score: 8.7,
  event_state: "developing",
  occurred_at: new Date(Date.now() - 3600_000).toISOString(),
  independent_source_count: 4,
  corroboration_level: "well_corroborated",
};

describe("EventRow", () => {
  it("shows severity, confidence and priority as distinct figures", () => {
    render(<EventRow event={event} onSelect={() => {}} />);
    expect(screen.getByText("9.2")).toBeInTheDocument();
    expect(screen.getByText("81%")).toBeInTheDocument();
    expect(screen.getByText("flash")).toBeInTheDocument();
    expect(screen.getByText("4 indep. sources")).toBeInTheDocument();
  });

  it("says n/a instead of zero when a score is missing", () => {
    render(<EventRow event={{ id: 2, title: "Unassessed report", severity: null, confidence: null }} onSelect={() => {}} />);
    expect(screen.getAllByText("n/a")).toHaveLength(2);
    expect(screen.getByText("Location unresolved")).toBeInTheDocument();
    expect(screen.getByText("time unknown")).toBeInTheDocument();
  });

  it("fires the selection callback with the event", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<EventRow event={event} onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: /earthquake/ }));
    expect(onSelect).toHaveBeenCalledWith(event);
  });
});

describe("primitives", () => {
  it("renders an em dash for an unavailable statistic", () => {
    render(<Stat label="Active events" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats count statistics with the right unit", () => {
    render(<Stat label="Alerts" value={3} format="count" hint="alert" />);
    expect(screen.getByText("3 alerts")).toBeInTheDocument();
  });

  it("labels a panel with a heading", () => {
    render(<Panel title="Coverage" eyebrow="HOW COMPLETE">body</Panel>);
    expect(screen.getByRole("heading", { name: "Coverage" })).toBeInTheDocument();
    expect(screen.getByText("HOW COMPLETE")).toBeInTheDocument();
  });
});

describe("CommandPalette", () => {

  it("lists navigation commands before any query", async () => {
    render(<CommandPalette open onClose={() => {}} onNavigate={() => {}} onOpenEvent={() => {}} onOpenCountry={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Search and commands" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Go to Overview/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Search query")).toHaveFocus());
  });

  it("searches stored reporting and opens a result", async () => {
    const onOpenEvent = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CommandPalette open onClose={onClose} onNavigate={() => {}} onOpenEvent={onOpenEvent} onOpenCountry={() => {}} />);

    await user.type(screen.getByLabelText("Search query"), "ceasefire");
    await waitFor(() => expect(screen.getByRole("option", { name: /Ceasefire talks resume/ })).toBeInTheDocument());
    expect(screen.getByRole("option", { name: /United Nations/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Syria/ })).toBeInTheDocument();

    await user.click(screen.getByRole("option", { name: /Ceasefire talks resume/ }));
    expect(onOpenEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 11 }));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape and navigates with the keyboard", async () => {
    const onClose = vi.fn();
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<CommandPalette open onClose={onClose} onNavigate={onNavigate} onOpenEvent={() => {}} onOpenCountry={() => {}} />);

    // Focus lands asynchronously, so wait for it before sending keys.
    await waitFor(() => expect(screen.getByLabelText("Search query")).toHaveFocus());
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onNavigate).toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <CommandPalette open={false} onClose={() => {}} onNavigate={() => {}} onOpenEvent={() => {}} onOpenCountry={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ConfidenceExplanation", () => {
  it("renders the structured explanation object without crashing", () => {
    render(
      <ConfidenceExplanation
        explanation={{
          summary: "Intelligence confidence is 72% (corroborated by multiple independent publishers)",
          corroboration_level: "well_corroborated",
          corroboration_description: "corroborated by multiple independent publishers",
          independent_publishers: 4,
          syndicated_publishers: 2,
          publisher_families: ["Wire A", "Wire B"],
          duplicate_pairs: [],
          limitations: ["The incident time is approximate or unknown."],
          state_reason: "New reports within the last day",
        }}
      />
    );
    expect(screen.getByText(/Intelligence confidence is 72%/)).toBeInTheDocument();
    expect(screen.getByText(/4 independent publishers/)).toBeInTheDocument();
    expect(screen.getByText(/incident time is approximate/)).toBeInTheDocument();
  });

  it("still renders a plain string explanation", () => {
    render(<ConfidenceExplanation explanation="Single-source report." />);
    expect(screen.getByText("Single-source report.")).toBeInTheDocument();
  });
});
