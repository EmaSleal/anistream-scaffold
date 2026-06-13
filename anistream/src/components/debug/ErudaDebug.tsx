"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

export function ErudaDebug() {
  const params = useSearchParams();
  const enabled = params.get("eruda") === "1";

  useEffect(() => {
    if (!enabled) return;

    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/eruda";
    document.body.appendChild(script);
    script.onload = () => {
      (window as Window & { eruda?: { init: () => void } }).eruda?.init();
    };

    return () => {
      document.body.removeChild(script);
    };
  }, [enabled]);

  return null;
}
