import { useEffect, useRef, useState } from "react";
import usePrefersReducedMotion from "./usePrefersReducedMotion";

export function easeOutCubic(t) {
  const clamped = Math.max(0, Math.min(1, t));
  return 1 - Math.pow(1 - clamped, 3);
}

export default function useCountUp(target, { duration = 800 } = {}) {
  const numericTarget = Number(target);
  const finalValue = Number.isFinite(numericTarget) ? numericTarget : 0;
  const prefersReducedMotion = usePrefersReducedMotion();
  const [value, setValue] = useState(() =>
    prefersReducedMotion ? finalValue : 0
  );
  const frameRef = useRef(null);

  useEffect(() => {
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current);

    if (prefersReducedMotion || duration <= 0) {
      setValue(finalValue);
      return undefined;
    }

    const start = performance.now();
    const from = 0;

    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      setValue(from + (finalValue - from) * easeOutCubic(progress));

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        frameRef.current = null;
      }
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [finalValue, duration, prefersReducedMotion]);

  return Number.isFinite(value) ? value : 0;
}
