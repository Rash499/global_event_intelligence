import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import Navbar from "./Navbar";

expect.extend(toHaveNoViolations);

const setup = (props = {}) => {
  const handlers = {
    onOverview: vi.fn(), onDashboard: vi.fn(), onWeather: vi.fn(), onAssistant: vi.fn(),
    onCollect: vi.fn(), onLogout: vi.fn(),
  };
  const user = userEvent.setup();
  const utils = render(<Navbar user={{ display_name: "Rashmika", email: "r@example.com" }} {...handlers} {...props} />);
  return { user, ...handlers, ...utils };
};

describe("Navbar", () => {
  it("routes each nav item to its handler", async () => {
    const { user, onOverview, onDashboard, onWeather, onAssistant } = setup();
    await user.click(screen.getByRole("button", { name: /Overview/ }));
    await user.click(screen.getByRole("button", { name: /Analytics/ }));
    await user.click(screen.getByRole("button", { name: /Weather/ }));
    await user.click(screen.getByRole("button", { name: /AI Assistant/ }));
    expect(onOverview).toHaveBeenCalledTimes(1); expect(onDashboard).toHaveBeenCalledTimes(1);
    expect(onWeather).toHaveBeenCalledTimes(1); expect(onAssistant).toHaveBeenCalledTimes(1);
  });
  it("the brand button goes home", async () => { const { user, onOverview } = setup(); await user.click(screen.getByRole("button", { name: "Global Event Intelligence home" })); expect(onOverview).toHaveBeenCalled(); });
  it("marks exactly the active item with aria-current", () => { setup({ activeView: "weather" }); const current = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "page"); expect(current).toHaveLength(1); expect(current[0]).toHaveTextContent("Weather"); expect(current[0]).toHaveClass("active"); });
  it("disables Collect News while collecting", () => { setup({ collecting: true }); expect(screen.getByRole("button", { name: /Collecting/ })).toBeDisabled(); });
  it("triggers collection", async () => { const { user, onCollect } = setup(); await user.click(screen.getByRole("button", { name: /Collect News/ })); expect(onCollect).toHaveBeenCalledTimes(1); });
  it("shows the user's initial and falls back gracefully", () => { const { unmount } = setup(); expect(screen.getByText("R")).toBeInTheDocument(); unmount(); render(<Navbar user={null} />); expect(screen.getByText("U")).toBeInTheDocument(); expect(screen.getByText("User")).toBeInTheDocument(); });
  describe("account menu", () => {
    it("opens, shows the email and signs out", async () => { const { user, onLogout } = setup(); const trigger = screen.getByRole("button", { name: /Rashmika/ }); expect(trigger).toHaveAttribute("aria-expanded", "false"); await user.click(trigger); expect(trigger).toHaveAttribute("aria-expanded", "true"); expect(screen.getByText("r@example.com")).toBeInTheDocument(); await user.click(screen.getByRole("menuitem", { name: "Sign out" })); expect(onLogout).toHaveBeenCalledTimes(1); });
    it("closes on Escape", async () => { const { user } = setup(); await user.click(screen.getByRole("button", { name: /Rashmika/ })); await user.keyboard("{Escape}"); expect(screen.queryByRole("menu")).not.toBeInTheDocument(); });
    it("closes on an outside click but not on an inside one", async () => { const { user } = setup(); await user.click(screen.getByRole("button", { name: /Rashmika/ })); await user.click(screen.getByText("r@example.com")); expect(screen.getByRole("menu")).toBeInTheDocument(); await user.click(document.body); expect(screen.queryByRole("menu")).not.toBeInTheDocument(); });
  });
  it("adds a scrolled style after the page scrolls", () => { setup(); const nav = screen.getByRole("navigation", { name: "Main" }); expect(nav).not.toHaveClass("is-scrolled"); act(() => { Object.defineProperty(window, "scrollY", { value: 120, configurable: true }); window.dispatchEvent(new Event("scroll")); }); expect(nav).toHaveClass("is-scrolled"); });
  it("has no axe violations", async () => { const { container } = setup(); expect(await axe(container)).toHaveNoViolations(); });
});
