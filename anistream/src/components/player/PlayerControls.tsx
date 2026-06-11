"use client";

import type { PlayerState } from "@/types";
import { ProgressBar } from "./ProgressBar";
import { formatDuration, cn } from "@/lib/utils";
import styles from "./PlayerControls.module.css";

interface PlayerControlsProps {
  state: PlayerState;
  onTogglePlay: () => void;
  onSeek: (s: number) => void;
  onSkip: (delta: number) => void;
  onToggleMute: () => void;
  onSetVolume: (v: number) => void;
  onSetPlaybackRate: (rate: number) => void;
  onToggleFullscreen: () => void;
  show: boolean;
}

const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];

export function PlayerControls({
  state,
  onTogglePlay,
  onSeek,
  onSkip,
  onToggleMute,
  onSetVolume,
  onSetPlaybackRate,
  onToggleFullscreen,
  show,
}: PlayerControlsProps) {
  const rateIndex = PLAYBACK_RATES.indexOf(state.playbackRate);
  const nextRate = PLAYBACK_RATES[(rateIndex + 1) % PLAYBACK_RATES.length] ?? 1;
  const fillPct = Math.round((state.isMuted ? 0 : state.volume) * 100);

  return (
    <div className={cn(styles.controls, !show && styles.hidden)} aria-hidden={!show} onClick={(e) => e.stopPropagation()}>
      <ProgressBar
        currentTime={state.currentTime}
        duration={state.duration}
        onSeek={onSeek}
      />

      <div className={styles.bar}>
        <div className={styles.left}>
          <button
            className={styles.iconBtn}
            onClick={() => onSkip(-10)}
            aria-label="Rewind 10 seconds"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12.5 3a9 9 0 1 0 9 9h-2a7 7 0 1 1-7-7V3z"/>
              <path d="M15 3H9v2h6V3z"/>
              <text x="8" y="15" fontSize="7" fontWeight="bold" fill="currentColor">10</text>
            </svg>
          </button>

          <button
            className={styles.playBtn}
            onClick={onTogglePlay}
            aria-label={state.isPlaying ? "Pause" : "Play"}
          >
            {state.isPlaying ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
            )}
          </button>

          <button
            className={styles.iconBtn}
            onClick={() => onSkip(10)}
            aria-label="Forward 10 seconds"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M11.5 3a9 9 0 1 1-9 9h2a7 7 0 1 0 7-7V3z"/>
              <path d="M9 3h6v2H9V3z"/>
              <text x="8" y="15" fontSize="7" fontWeight="bold" fill="currentColor">10</text>
            </svg>
          </button>

          <div className={styles.volumeGroup}>
            <button
              className={styles.iconBtn}
              onClick={onToggleMute}
              aria-label={state.isMuted ? "Unmute" : "Mute"}
            >
              {state.isMuted || state.volume === 0 ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                </svg>
              )}
            </button>
            <div className={styles.volumePopup} role="group" aria-label="Volume">
              <span className={styles.volumePct}>
                {Math.round(state.isMuted ? 0 : state.volume * 100)}%
              </span>
              <input
                type="range"
                className={styles.volumeSlider}
                min={0}
                max={1}
                step={0.05}
                value={state.isMuted ? 0 : state.volume}
                onChange={(e) => onSetVolume(Number(e.target.value))}
                aria-label="Volume"
                style={{
                  background: `linear-gradient(to top, #f47521 ${fillPct}%, transparent ${fillPct}%)`,
                }}
              />
            </div>
          </div>

          <time className={styles.time} dateTime={`PT${Math.floor(state.currentTime)}S`}>
            {formatDuration(state.currentTime)}
            <span className={styles.timeSep}> / </span>
            {formatDuration(state.duration)}
          </time>
        </div>

        <div className={styles.right}>
          <button className={styles.iconBtn} aria-label="Subtitles">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="2" y="7" width="20" height="15" rx="2"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="7" y1="16" x2="13" y2="16"/>
            </svg>
          </button>

          <button
            className={styles.rateBtn}
            onClick={() => onSetPlaybackRate(nextRate)}
            aria-label={`Playback speed: ${state.playbackRate}x`}
          >
            {state.playbackRate}x
          </button>

          <button
            className={styles.iconBtn}
            onClick={onToggleFullscreen}
            aria-label={state.isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            {state.isFullscreen ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
