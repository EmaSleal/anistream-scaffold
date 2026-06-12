"use client";

import { useState, useTransition } from "react";
import { Select } from "@/components/ui/Select";
import { toggleWatchlist } from "@/app/actions/watchlist";
import styles from "./AnimeCard.module.css";

interface AnimeCardMenuProps {
  seriesId: string;
  isInWatchlist: boolean;
}

export function AnimeCardMenu({ seriesId, isInWatchlist }: AnimeCardMenuProps) {
  const [inList, setInList] = useState(isInWatchlist);
  const [, startTransition] = useTransition();

  const options = inList
    ? [{ label: "Remove from My List", value: "remove" }]
    : [{ label: "Add to My List", value: "add" }];

  function handleChange(_value: string) {
    // Optimistic flip — revalidatePath inside toggleWatchlist reconciles on next render
    setInList((prev) => !prev);
    startTransition(() => {
      void toggleWatchlist(seriesId);
    });
  }

  return (
    // Stop click propagation here so the wrapping <Link> in AnimeCard does not navigate
    // when the user interacts with the menu trigger or dropdown.
    <div
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <Select
        options={options}
        placeholder="···"
        onChange={handleChange}
        className={styles.menuBtn}
        aria-label="More options"
      />
    </div>
  );
}
