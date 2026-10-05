import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AlertToast from "./AlertToast";
describe("AlertToast", () => {
  it("renders nothing without a message", () => { const { container } = render(<AlertToast message="" onDismiss={() => {}} />); expect(container).toBeEmptyDOMElement(); });
  it("announces the message as an alert", () => { render(<AlertToast message="3 new events detected" onDismiss={() => {}} />); expect(screen.getByRole("alert")).toHaveTextContent("3 new events detected"); });
  it("dismisses on click", async () => { const onDismiss = vi.fn(); render(<AlertToast message="hi" onDismiss={onDismiss} />); await userEvent.click(screen.getByRole("button", { name: /dismiss/i })); expect(onDismiss).toHaveBeenCalledTimes(1); });
  it("auto-dismisses after eight seconds, not before", () => { vi.useFakeTimers(); const onDismiss = vi.fn(); render(<AlertToast message="hi" onDismiss={onDismiss} />); act(() => vi.advanceTimersByTime(7999)); expect(onDismiss).not.toHaveBeenCalled(); act(() => vi.advanceTimersByTime(1)); expect(onDismiss).toHaveBeenCalledTimes(1); });
  it("clears the timer when unmounted", () => { vi.useFakeTimers(); const onDismiss = vi.fn(); const { unmount } = render(<AlertToast message="hi" onDismiss={onDismiss} />); unmount(); act(() => vi.advanceTimersByTime(10_000)); expect(onDismiss).not.toHaveBeenCalled(); });
});
