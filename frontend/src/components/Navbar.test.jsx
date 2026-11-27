import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import Navbar from "./Navbar";
import { workspaceSections } from "../navigation/workspaceNav";

expect.extend(toHaveNoViolations);

const setup = (props = {}) => {
  const handlers = {
    onNavigate: vi.fn(), onOverview: vi.fn(), onOpenSearch: vi.fn(), onCollect: vi.fn(), onLogout: vi.fn(),
  };
  const user = userEvent.setup();
  const utils = render(<Navbar user={{ display_name: "Rashmika", email: "r@example.com" }} {...handlers} {...props} />);
  return { user, ...handlers, ...utils };
};

describe("Navbar", () => {
  it("renders every workspace section once", () => {
    setup();
    for (const section of workspaceSections) {
      expect(screen.getAllByRole("button", { name: new RegExp(section.label) })).toHaveLength(1);
    }
  });

  it("routes overview to its dedicated handler and other sections through onNavigate", async () => {
    const { user, onOverview, onNavigate } = setup();
    await user.click(screen.getByRole("button", { name: /Overview/ }));
    expect(onOverview).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /Providers/ }));
    expect(onNavigate).toHaveBeenCalledWith("providers");
    await user.click(screen.getByRole("button", { name: /System/ }));
    expect(onNavigate).toHaveBeenCalledWith("system");
  });

  it("the brand button goes home", async () => {
    const { user, onOverview } = setup();
    await user.click(screen.getByRole("button", { name: "Global Event Intelligence home" }));
    expect(onOverview).toHaveBeenCalled();
  });

  it("marks exactly the active item with aria-current", () => {
    setup({ activeView: "alerts" });
    const current = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Alerts");
    expect(current[0]).toHaveClass("active");
  });

  it("shows the unread alert count only when there are new alerts", () => {
    const { unmount } = setup({ alertCount: 4 });
    expect(screen.getByLabelText("4 new alerts")).toHaveTextContent("4");
    unmount();
    setup({ alertCount: 0 });
    expect(screen.queryByLabelText(/new alerts/)).not.toBeInTheDocument();
  });

  it("summarises provider health without inventing a status", () => {
    const { unmount } = setup({ providerHealth: { healthy: 3, degraded: 1, unavailable: 0, not_configured: 2 } });
    expect(screen.getByRole("button", { name: /Provider health/ })).toHaveAttribute("title", "3 healthy, 1 degraded, 0 unavailable, 2 not configured");
    expect(screen.getByRole("button", { name: /Provider health/ })).toHaveTextContent("Feed issues");
    unmount();
    setup();
    expect(screen.getByRole("button", { name: /Provider health/ })).toHaveTextContent("Feeds");
  });

  it("opens the command palette", async () => {
    const { user, onOpenSearch } = setup();
    await user.click(screen.getByRole("button", { name: /Search events, countries and sources/ }));
    expect(onOpenSearch).toHaveBeenCalledTimes(1);
  });

  it("disables collection while collecting", () => {
    setup({ collecting: true });
    expect(screen.getByRole("button", { name: /Collecting/ })).toBeDisabled();
  });

  it("triggers collection", async () => {
    const { user, onCollect } = setup();
    await user.click(screen.getByRole("button", { name: /Collect/ }));
    expect(onCollect).toHaveBeenCalledTimes(1);
  });

  it("shows the user's initial and falls back gracefully", () => {
    const { unmount } = setup();
    expect(screen.getByText("R")).toBeInTheDocument();
    unmount();
    render(<Navbar user={null} />);
    expect(screen.getByText("U")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
  });

  it("toggles the collapsed sections menu", async () => {
    const { user } = setup();
    const burger = screen.getByRole("button", { name: /Sections/ });
    expect(burger).toHaveAttribute("aria-expanded", "false");
    await user.click(burger);
    expect(burger).toHaveAttribute("aria-expanded", "true");
    await user.click(screen.getByRole("button", { name: /Reports/ }));
    expect(burger).toHaveAttribute("aria-expanded", "false");
  });

  describe("account menu", () => {
    it("opens, shows the email and signs out", async () => {
      const { user, onLogout } = setup();
      const trigger = screen.getByRole("button", { name: /Rashmika/ });
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      await user.click(trigger);
      expect(trigger).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("r@example.com")).toBeInTheDocument();
      await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
      expect(onLogout).toHaveBeenCalledTimes(1);
    });

    it("closes on Escape", async () => {
      const { user } = setup();
      await user.click(screen.getByRole("button", { name: /Rashmika/ }));
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    });

    it("closes on an outside click but not on an inside one", async () => {
      const { user } = setup();
      await user.click(screen.getByRole("button", { name: /Rashmika/ }));
      await user.click(screen.getByText("r@example.com"));
      expect(screen.getByRole("menu")).toBeInTheDocument();
      await user.click(document.body);
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    });
  });

  it("adds a scrolled style after the page scrolls", () => {
    setup();
    const nav = screen.getByRole("navigation", { name: "Workspace" });
    expect(nav).not.toHaveClass("is-scrolled");
    act(() => {
      Object.defineProperty(window, "scrollY", { value: 120, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });
    expect(nav).toHaveClass("is-scrolled");
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    expect(await axe(container)).toHaveNoViolations();
  });
});
