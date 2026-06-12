"use client";

import { useState, useRef, useEffect, useTransition } from "react";
import { toggleWatchlist } from "@/app/actions/watchlist";
import styles from "./AnimeCard.module.css";

interface AnimeCardMenuProps {
  seriesId: string;
  isInWatchlist: boolean;
}

export function AnimeCardMenu({ seriesId, isInWatchlist }: AnimeCardMenuProps) {
  const [open, setOpen] = useState(false);
  const [inList, setInList] = useState(isInWatchlist);
  const [, startTransition] = useTransition();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open]);

  function handleTrigger(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setOpen((prev) => !prev);
  }

  function handleAction(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setOpen(false);
    setInList((prev) => !prev);
    startTransition(() => {
      void toggleWatchlist(seriesId);
    });
  }

  return (
    <div
      ref={containerRef}
      style={{ position: "relative" }}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
    >
      <button
        className={styles.menuBtn}
        aria-label="More options"
        aria-expanded={open}
        onClick={handleTrigger}
      >
        ···
      </button>

      {open && (
        <div className={styles.menuDropdown}>
          <button className={styles.menuItem} onMouseDown={handleAction}>
            {inList ? "Remove from My List" : "Add to My List"}
          </button>
        </div>
      )}
    </div>
  );
}
