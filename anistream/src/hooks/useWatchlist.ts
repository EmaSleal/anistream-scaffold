"use client";

import { useCallback, useEffect, useState } from "react";
import type { WatchlistItem } from "@/types";

const STORAGE_KEY = "anistream_watchlist";

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setWatchlist(JSON.parse(stored) as WatchlistItem[]);
    } catch {
      // localStorage may not be available
    }
  }, []);

  const persist = useCallback((items: WatchlistItem[]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      // noop
    }
    setWatchlist(items);
  }, []);

  const isInWatchlist = useCallback(
    (seriesId: string) => watchlist.some((w) => w.seriesId === seriesId),
    [watchlist]
  );

  const addToWatchlist = useCallback(
    (seriesId: string) => {
      if (isInWatchlist(seriesId)) return;
      persist([...watchlist, { seriesId, addedAt: new Date().toISOString() }]);
    },
    [watchlist, isInWatchlist, persist]
  );

  const removeFromWatchlist = useCallback(
    (seriesId: string) => {
      persist(watchlist.filter((w) => w.seriesId !== seriesId));
    },
    [watchlist, persist]
  );

  const toggleWatchlist = useCallback(
    (seriesId: string) => {
      isInWatchlist(seriesId)
        ? removeFromWatchlist(seriesId)
        : addToWatchlist(seriesId);
    },
    [isInWatchlist, addToWatchlist, removeFromWatchlist]
  );

  return { watchlist, isInWatchlist, toggleWatchlist };
}
