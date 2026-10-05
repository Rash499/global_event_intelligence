import useCountUp from "../../hooks/useCountUp";

/** Renders a number that counts up when it first appears or changes. */
export default function AnimatedNumber({ value, duration, format }) {
  const shown = useCountUp(value, { duration });
  return <>{format ? format(shown) : shown.toLocaleString()}</>;
}
