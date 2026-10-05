import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { categories } from "../types.jsx";
import CategoryFilter from "./CategoryFilter";
expect.extend(toHaveNoViolations);
describe("CategoryFilter", () => {
  it("renders one button per category with humanised labels", () => { render(<CategoryFilter selectedCategory="all" onChange={() => {}} />); expect(screen.getAllByRole("button")).toHaveLength(categories.length); expect(screen.getByRole("button", { name: "natural disaster" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "crime security" })).toBeInTheDocument(); });
  it("marks only the selected category as pressed", () => { render(<CategoryFilter selectedCategory="health" onChange={() => {}} />); const pressed = screen.getAllByRole("button").filter((b) => b.getAttribute("aria-pressed") === "true"); expect(pressed).toHaveLength(1); expect(pressed[0]).toHaveTextContent("health"); expect(pressed[0]).toHaveClass("active"); });
  it("shows the current selection in the heading", () => { const { rerender } = render(<CategoryFilter selectedCategory="all" onChange={() => {}} />); expect(document.querySelector(".filter-selection")).toHaveTextContent("All signals"); rerender(<CategoryFilter selectedCategory="natural_disaster" onChange={() => {}} />); expect(document.querySelector(".filter-selection")).toHaveTextContent("natural disaster"); });
  it("reports the raw category key on click and via keyboard", async () => { const onChange = vi.fn(); const user = userEvent.setup(); render(<CategoryFilter selectedCategory="all" onChange={onChange} />); await user.click(screen.getByRole("button", { name: "conflict" })); expect(onChange).toHaveBeenLastCalledWith("conflict"); screen.getByRole("button", { name: "science" }).focus(); await user.keyboard("{Enter}"); expect(onChange).toHaveBeenLastCalledWith("science"); });
  it("has no axe violations", async () => { const { container } = render(<CategoryFilter selectedCategory="all" onChange={() => {}} />); expect(await axe(container)).toHaveNoViolations(); });
});
