import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import usePrefersReducedMotion from "./usePrefersReducedMotion";
import useCountUp, { easeOutCubic } from "./useCountUp";
import useScrolled from "./useScrolled";

const setReduced = (value) => globalThis.__setReducedMotion(value);

describe("easeOutCubic", () => {
  it("starts at 0, ends at 1 and is monotonic", () => {
    expect(easeOutCubic(0)).toBe(0); expect(easeOutCubic(1)).toBe(1);
    let previous = -1;
    for (let t=0;t<=1;t+=0.1) { const value=easeOutCubic(t); expect(value).toBeGreaterThanOrEqual(previous); previous=value; }
  });
});
describe("usePrefersReducedMotion", () => {
  it("reflects the media query and reacts to changes", () => {
    const {result}=renderHook(()=>usePrefersReducedMotion()); expect(result.current).toBe(true);
    act(()=>setReduced(false)); expect(result.current).toBe(false);
  });
});
describe("useCountUp", () => {
  it("returns the final value immediately when motion is reduced", () => { const {result}=renderHook(()=>useCountUp(42)); expect(result.current).toBe(42); });
  it("treats a non-numeric target as 0", () => { const {result}=renderHook(()=>useCountUp("abc")); expect(result.current).toBe(0); });
  it("counts up when motion is allowed", () => {
    setReduced(false); vi.useFakeTimers({toFake:["requestAnimationFrame","cancelAnimationFrame","performance"]});
    const {result}=renderHook(()=>useCountUp(100,{duration:500})); expect(result.current).toBe(0);
    act(()=>vi.advanceTimersByTime(250)); expect(result.current).toBeGreaterThan(0); expect(result.current).toBeLessThan(100);
    act(()=>vi.advanceTimersByTime(600)); expect(result.current).toBe(100);
  });
});
describe("useScrolled", () => {
  const setScroll=(y)=>{Object.defineProperty(window,"scrollY",{value:y,configurable:true});window.dispatchEvent(new Event("scroll"));};
  it("flips after the threshold",()=>{setScroll(0);const {result}=renderHook(()=>useScrolled(20));expect(result.current).toBe(false);act(()=>setScroll(21));expect(result.current).toBe(true);});
  it("removes its listener on unmount",()=>{const remove=vi.spyOn(window,"removeEventListener");const {unmount}=renderHook(()=>useScrolled());unmount();expect(remove).toHaveBeenCalledWith("scroll",expect.any(Function));});
});
