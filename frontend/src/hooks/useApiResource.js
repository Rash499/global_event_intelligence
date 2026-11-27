import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Small data-fetching hook for the workspace views.
 *
 * Deliberately not a cache library: the views need loading/error/refresh with
 * honest error messages, request cancellation on unmount, and a manual
 * `reload`. Anything a library would hide (a swallowed error, a stale "ok")
 * is surfaced here instead.
 *
 * @param {Function} fetcher async function; called with () => data
 * @param {Array} deps dependency list; a change refetches
 * @param {{enabled?: boolean, initialData?: any, pollMs?: number}} options
 */
export function useApiResource(fetcher, deps = [], options = {}) {
  const { enabled = true, initialData = null, pollMs = 0 } = options;
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const mounted = useRef(true);
  const requestId = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await fetcherRef.current();
      if (!mounted.current || id !== requestId.current) return;
      setData(result);
      setUpdatedAt(new Date().toISOString());
    } catch (caught) {
      if (!mounted.current || id !== requestId.current) return;
      setError(caught);
    } finally {
      if (mounted.current && id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps]);

  useEffect(() => {
    if (!enabled || !pollMs) return undefined;
    const timer = window.setInterval(run, pollMs);
    return () => window.clearInterval(timer);
  }, [enabled, pollMs, run]);

  return { data, loading, error, updatedAt, reload: run, setData };
}

export default useApiResource;
