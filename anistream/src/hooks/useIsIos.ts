"use client";

import { useEffect, useState } from "react";
import { isIosClient } from "@/lib/isIosClient";

/**
 * Mount-safe iOS detection hook.
 *
 * Returns `null` until the component mounts (avoids SSR hydration mismatch),
 * then resolves to `true` (iOS) or `false` (non-iOS).
 */
export function useIsIos(): boolean | null {
  const [isIos, setIsIos] = useState<boolean | null>(null);

  useEffect(() => {
    setIsIos(
      isIosClient(
        navigator.userAgent,
        navigator.maxTouchPoints ?? 0,
      )
    );
  }, []);

  return isIos;
}
