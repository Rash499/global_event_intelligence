import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

let reduced = true;
const listeners = new Set<(e: { matches: boolean }) => void>();

export function setReducedMotion(value: boolean) {
  reduced = value;
  listeners.forEach((fn) => fn({ matches: value }));
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    get matches() { return query.includes("prefers-reduced-motion") ? reduced : false; },
    media: query,
    addEventListener: (_: string, fn: (e: { matches: boolean }) => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: (e: { matches: boolean }) => void) => listeners.delete(fn),
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    onchange: null,
  }),
});

(globalThis as any).__setReducedMotion = setReducedMotion;

afterEach(() => {
  cleanup();
  reduced = true;
});
