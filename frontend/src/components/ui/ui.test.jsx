import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";

import AnimatedNumber from "./AnimatedNumber";
import HeroBackdrop from "./HeroBackdrop";
import PageTransition from "./PageTransition";
import { EventListSkeleton, Skeleton, ViewFallback } from "./Skeleton";

expect.extend(toHaveNoViolations);

describe("AnimatedNumber", () => {
  it("renders a localised number", () => {
    render(<AnimatedNumber value={12345} />);
    expect(screen.getByText((12345).toLocaleString())).toBeInTheDocument();
  });

  it("supports a custom formatter", () => {
    render(<AnimatedNumber value={7} format={(n) => `${n} events`} />);
    expect(screen.getByText("7 events")).toBeInTheDocument();
  });
});

describe("Skeleton family", () => {
  it("Skeleton is hidden from assistive tech", () => {
    const { container } = render(<Skeleton className="x" />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
    expect(container.firstChild).toHaveClass("skeleton", "x");
  });

  it("EventListSkeleton exposes one status region and the requested count", () => {
    const { container } = render(<EventListSkeleton count={3} />);
    expect(screen.getByRole("status", { name: "Loading events" })).toBeInTheDocument();
    expect(container.querySelectorAll(".event-skeleton")).toHaveLength(3);
  });

  it("staggers skeleton cards with an index variable", () => {
    const { container } = render(<EventListSkeleton count={2} />);
    const cards = container.querySelectorAll(".event-skeleton");
    expect(cards[0].style.getPropertyValue("--i")).toBe("0");
    expect(cards[1].style.getPropertyValue("--i")).toBe("1");
  });

  it("ViewFallback has an accessible label", () => {
    render(<ViewFallback label="Loading analytics" />);
    expect(screen.getByRole("status", { name: "Loading analytics" })).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(<ViewFallback />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("PageTransition", () => {
  it("remounts its children when the view key changes", () => {
    let mounts = 0;
    const Probe = () => {
      mounts += 1;
      return <span>probe</span>;
    };
    const { rerender } = render(<PageTransition viewKey="a"><Probe /></PageTransition>);
    const first = screen.getByText("probe");
    rerender(<PageTransition viewKey="a"><Probe /></PageTransition>);
    expect(screen.getByText("probe")).toBe(first);
    rerender(<PageTransition viewKey="b"><Probe /></PageTransition>);
    expect(screen.getByText("probe")).not.toBe(first);
    expect(document.querySelector("[data-view='b']")).toBeInTheDocument();
  });
});

describe("HeroBackdrop", () => {
  it("is purely decorative", () => {
    const { container } = render(<HeroBackdrop />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll(".hero-orb")).toHaveLength(2);
  });
});
