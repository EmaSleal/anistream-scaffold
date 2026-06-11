"use client";

import { useEffect } from "react";
import { refreshSimulcastAction } from "@/app/actions/simulcast";

interface Props {
  seriesId: string;
}

/**
 * Invisible client component that fires a simulcast refresh on mount.
 *
 * Calls refreshSimulcastAction without await so the page is never blocked.
 * Renders nothing — returns null.
 *
 * Pattern mirrors IngestTrigger.tsx: mount-time side effect, no visible UI.
 */
export default function SimulcastRefreshTrigger({ seriesId }: Props) {
  useEffect(() => {
    // Fire-and-forget: do not await, do not block render
    refreshSimulcastAction(seriesId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
