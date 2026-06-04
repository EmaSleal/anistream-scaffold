"use client";

import { useRef } from "react";
import { clamp, formatDuration } from "@/lib/utils";
import styles from "./ProgressBar.module.css";

interface ProgressBarProps {
  currentTime: number;
  duration: number;
  onSeek: (seconds: number) => void;
}

export function ProgressBar({ currentTime, duration, onSeek }: ProgressBarProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  const seekFromX = (clientX: number) => {
    const track = trackRef.current;
    if (!track || duration === 0) return;
    const rect = track.getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    onSeek(ratio * duration);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    isDragging.current = true;
    seekFromX(e.clientX);

    const onMouseMove = (e: MouseEvent) => {
      if (isDragging.current) seekFromX(e.clientX);
    };

    const onMouseUp = (e: MouseEvent) => {
      isDragging.current = false;
      seekFromX(e.clientX);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    isDragging.current = true;
    seekFromX(e.touches[0].clientX);

    const onTouchMove = (e: TouchEvent) => {
      if (isDragging.current) seekFromX(e.touches[0].clientX);
    };

    const onTouchEnd = (e: TouchEvent) => {
      isDragging.current = false;
      if (e.changedTouches[0]) seekFromX(e.changedTouches[0].clientX);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
    };

    document.addEventListener("touchmove", onTouchMove, { passive: true });
    document.addEventListener("touchend", onTouchEnd);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight") onSeek(currentTime + 5);
    if (e.key === "ArrowLeft") onSeek(currentTime - 5);
  };

  return (
    <div className={styles.wrapper}>
      <div
        ref={trackRef}
        className={styles.track}
        role="slider"
        aria-label="Video progress"
        aria-valuemin={0}
        aria-valuemax={duration}
        aria-valuenow={Math.floor(currentTime)}
        aria-valuetext={`${formatDuration(currentTime)} of ${formatDuration(duration)}`}
        tabIndex={0}
        onMouseDown={handleMouseDown}
        onTouchStart={handleTouchStart}
        onKeyDown={handleKeyDown}
      >
        <div className={styles.fill} style={{ width: `${progress}%` }}>
          <div className={styles.thumb} aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
