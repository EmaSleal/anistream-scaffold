"use client";

import { useEffect, useState } from "react";

/**
 * Returns true when the user has scrolled past `threshold` pixels.
 * Useful for navbar scroll-hide behavior.
 */
export function useScrollHide(threshold = 60): boolean {
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setIsScrolled(window.scrollY > threshold);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return isScrolled;
}
