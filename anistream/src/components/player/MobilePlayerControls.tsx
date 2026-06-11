"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import type { PlayerState } from "@/types";
import { cn, formatDuration } from "@/lib/utils";
import styles from "./MobilePlayerControls.module.css";

interface MobilePlayerControlsProps {
  state: PlayerState;
  onTogglePlay: () => void;
  onSkip: (delta: number) => void;
  onToggleFullscreen: () => void;
  onSeek: (t: number) => void;
  onRevealControls: () => void;
  nextEpisodeHref?: string;
  show: boolean;
}

export function MobilePlayerControls({
  state,
  onTogglePlay,
  onSkip,
  onToggleFullscreen,
  onSeek,
  onRevealControls,
  nextEpisodeHref,
  show,
}: MobilePlayerControlsProps) {
  const lastTapRef = useRef<{ time: number; half: "left" | "right" } | null>(null);
  const [seekFeedback, setSeekFeedback] = useState<"left" | "right" | null>(null);
  const [localSeek, setLocalSeek] = useState<number | null>(null);

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    e.stopPropagation();
    if (!show) {
      onRevealControls();
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const third = rect.width / 3;

    // Center third — no seek; if paused, start playing
    if (relX >= third && relX <= third * 2) {
      lastTapRef.current = null;
      if (!state.isPlaying) onTogglePlay();
      return;
    }

    const half: "left" | "right" = relX < third ? "left" : "right";
    const now = Date.now();
    const last = lastTapRef.current;

    if (last && last.half === half && now - last.time <= 300) {
      // Double tap detected
      lastTapRef.current = null;
      const delta = half === "left" ? -10 : 10;
      onSkip(delta);
      setSeekFeedback(half);
      setTimeout(() => setSeekFeedback(null), 600);
    } else {
      // Single tap — record for potential double-tap
      lastTapRef.current = { time: now, half };
    }
  }

  return (
    <div
      className={cn(styles.overlay, !show && styles.hidden)}
      onClick={handleOverlayClick}
    >
      {/* Seek feedback indicators */}
      <span
        className={cn(
          styles.seekFeedback,
          styles.seekFeedbackLeft,
          seekFeedback === "left" && styles.seekFeedbackVisible
        )}
        aria-hidden="true"
      >
        -10
      </span>
      <span
        className={cn(
          styles.seekFeedback,
          styles.seekFeedbackRight,
          seekFeedback === "right" && styles.seekFeedbackVisible
        )}
        aria-hidden="true"
      >
        +10
      </span>

      {/* Top-right: next episode + fullscreen */}
      <div className={styles.topRight}>
        {nextEpisodeHref && (
          <Link
            href={nextEpisodeHref as Route}
            className={styles.topBtn}
            aria-label="Next episode"
            onClick={(e) => e.stopPropagation()}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <polygon points="5 4 15 12 5 20 5 4" />
              <rect x="17" y="4" width="2" height="16" />
            </svg>
          </Link>
        )}
        <button
          className={styles.topBtn}
          onClick={(e) => {
            e.stopPropagation();
            onToggleFullscreen();
          }}
          aria-label={state.isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        >
          {state.isFullscreen ? (
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
            </svg>
          ) : (
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
            </svg>
          )}
        </button>
      </div>

      {/* Bottom: gradient + time + progress bar */}
      <div className={styles.bottomGradient}>
        <div className={styles.bottomBar}>
          <span className={styles.timeLabel}>
            {formatDuration(state.currentTime)}
          </span>
          <input
            type="range"
            className={styles.progressRange}
            min={0}
            max={state.duration || 1}
            step={1}
            value={localSeek ?? state.currentTime}
            onChange={(e) => setLocalSeek(Number(e.target.value))}
            onPointerUp={(e) => {
              const v = Number((e.target as HTMLInputElement).value);
              onSeek(v);
              setLocalSeek(null);
            }}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
            aria-label="Seek"
            style={{
              background: `linear-gradient(to right, #f47521 ${((localSeek ?? state.currentTime) / (state.duration || 1)) * 100}%, rgba(255,255,255,0.25) 0%)`,
            }}
          />
        </div>
      </div>

      {/* Center: skip-back, play/pause, skip-forward */}
      <div className={styles.center}>
        <button
          className={styles.iconBtn}
          onClick={(e) => {
            e.stopPropagation();
            onSkip(-10);
          }}
          aria-label="Rewind 10 seconds"
        >
          <svg
            width="33"
            height="33"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M12.5 3a9 9 0 1 0 9 9h-2a7 7 0 1 1-7-7V3z" />
            <path d="M15 3H9v2h6V3z" />
            <text x="8" y="15" fontSize="7" fontWeight="bold" fill="currentColor">
              10
            </text>
          </svg>
        </button>

        <button
          className={styles.playBtn}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePlay();
          }}
          aria-label={state.isPlaying ? "Pause" : "Play"}
        >
          {state.isPlaying ? (
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
          ) : (
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          )}
        </button>

        <button
          className={styles.iconBtn}
          onClick={(e) => {
            e.stopPropagation();
            onSkip(10);
          }}
          aria-label="Forward 10 seconds"
        >
          <svg
            width="33"
            height="33"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M11.5 3a9 9 0 1 1-9 9h2a7 7 0 1 0 7-7V3z" />
            <path d="M9 3h6v2H9V3z" />
            <text x="8" y="15" fontSize="7" fontWeight="bold" fill="currentColor">
              10
            </text>
          </svg>
        </button>
      </div>
    </div>
  );
}
