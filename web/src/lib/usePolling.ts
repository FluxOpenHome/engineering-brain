"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface PollingState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

/**
 * Fetch `load()` once, then re-run it every `intervalMs` for as long as
 * `shouldPoll(data)` returns true. Re-loads when `deps` change. Polling
 * restarts automatically if a later `refresh()` returns data that needs it.
 */
export function usePolling<T>(
  load: () => Promise<T>,
  shouldPoll: (data: T | null) => boolean,
  intervalMs: number,
  deps: React.DependencyList = [],
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;
  const shouldRef = useRef(shouldPoll);
  shouldRef.current = shouldPoll;

  const refresh = useCallback(async () => {
    try {
      const d = await loadRef.current();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setTick((t) => t + 1);
    }
  }, []);

  // Initial load and reload on deps change.
  useEffect(() => {
    setLoading(true);
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, ...deps]);

  // After each completed load, schedule the next one if still needed.
  useEffect(() => {
    if (tick === 0) return;
    if (!shouldRef.current(data)) return;
    const timer = setTimeout(() => void refresh(), intervalMs);
    return () => clearTimeout(timer);
  }, [tick, data, intervalMs, refresh]);

  return { data, error, loading, refresh };
}
