"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PlayerState } from "@/types";
import { clamp, debounce } from "@/lib/utils";

const CONTROLS_HIDE_DELAY = 2000;

interface UsePlayerControlsReturn {
  playerState: PlayerState;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  togglePlay: () => void;
  seek: (seconds: number) => void;
  setVolume: (volume: number) => void;
  toggleMute: () => void;
  setPlaybackRate: (rate: number) => void;
  toggleFullscreen: (containerRef: React.RefObject<HTMLDivElement | null>) => void;
  handleMouseMove: () => void;
  skipSeconds: (delta: number) => void;
  revealControls: () => void;
}

export function usePlayerControls(initialDuration = 0, initialTime = 0): UsePlayerControlsReturn {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoplayAttempted = useRef(false);

  const [playerState, setPlayerState] = useState<PlayerState>({
    isPlaying: false,
    currentTime: 0,
    duration: initialDuration,
    volume: 1,
    isMuted: false,
    playbackRate: 1,
    isFullscreen: false,
    showControls: true,
  });

  const scheduleHideControls = useCallback(() => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      setPlayerState((prev) =>
        prev.isPlaying ? { ...prev, showControls: false } : prev
      );
    }, CONTROLS_HIDE_DELAY);
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const handleMouseMove = useCallback(
    debounce(() => {
      setPlayerState((prev) => ({ ...prev, showControls: true }));
      scheduleHideControls();
    }, 50),
    [scheduleHideControls]
  );

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play().catch((err: unknown) => {
        if (err instanceof Error && err.name !== "AbortError") {
          console.error(err);
        }
      });
    } else {
      video.pause();
    }
  }, []);

  const seek = useCallback((seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = clamp(seconds, 0, video.duration || 0);
  }, []);

  const skipSeconds = useCallback((delta: number) => {
    const video = videoRef.current;
    if (!video) return;
    seek(video.currentTime + delta);
  }, [seek]);

  const setVolume = useCallback((volume: number) => {
    const video = videoRef.current;
    if (!video) return;
    const clamped = clamp(volume, 0, 1);
    video.volume = clamped;
    video.muted = clamped === 0;
    setPlayerState((prev) => ({
      ...prev,
      volume: clamped,
      isMuted: clamped === 0,
    }));
  }, []);

  const toggleMute = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setPlayerState((prev) => ({ ...prev, isMuted: !prev.isMuted }));
  }, []);

  const setPlaybackRate = useCallback((rate: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = rate;
    setPlayerState((prev) => ({ ...prev, playbackRate: rate }));
  }, []);

  const toggleFullscreen = useCallback(
    (containerRef: React.RefObject<HTMLDivElement | null>) => {
      const el = containerRef.current;
      if (!el) return;
      const isFs = !!(document.fullscreenElement ?? (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement);
      if (!isFs) {
        if (el.requestFullscreen) {
          void el.requestFullscreen();
        } else {
          // iOS Safari: requestFullscreen on div is unsupported — fall back to video element
          const video = el.querySelector("video");
          if (video && (video as HTMLVideoElement & { webkitEnterFullscreen?: () => void }).webkitEnterFullscreen) {
            (video as HTMLVideoElement & { webkitEnterFullscreen: () => void }).webkitEnterFullscreen();
          }
        }
      } else {
        if (document.exitFullscreen) {
          void document.exitFullscreen();
        } else {
          (document as Document & { webkitExitFullscreen?: () => void }).webkitExitFullscreen?.();
        }
      }
    },
    []
  );

  // Sync video events → state
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onPlay = () => {
      setPlayerState((p) => ({ ...p, isPlaying: true }));
      if (hideTimer.current) clearTimeout(hideTimer.current);
      hideTimer.current = setTimeout(() => {
        setPlayerState((prev) =>
          prev.isPlaying ? { ...prev, showControls: false } : prev
        );
      }, CONTROLS_HIDE_DELAY);
    };
    const onPause = () =>
      setPlayerState((p) => ({ ...p, isPlaying: false, showControls: true }));
    const onTimeUpdate = () =>
      setPlayerState((p) => ({ ...p, currentTime: video.currentTime }));
    const onDurationChange = () =>
      setPlayerState((p) => ({ ...p, duration: video.duration }));
    const onCanPlay = () => {
      if (autoplayAttempted.current) return;
      autoplayAttempted.current = true;
      video.play().catch((err: unknown) => {
        if (err instanceof Error && err.name !== "AbortError" && err.name !== "NotAllowedError") {
          console.error("[player] autoplay failed:", err.message);
        }
      });
    };

    const onLoadedMetadata = () => {
      if (initialTime > 0) {
        video.currentTime = Math.min(initialTime, video.duration);
      }
      setPlayerState((p) => ({ ...p, duration: video.duration }));
    };
    const onVolumeChange = () =>
      setPlayerState((p) => ({
        ...p,
        volume: video.volume,
        isMuted: video.muted,
      }));
    const onFullscreenChange = () =>
      setPlayerState((p) => ({
        ...p,
        isFullscreen: !!(document.fullscreenElement ?? (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement),
      }));

    video.addEventListener("canplay", onCanPlay);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("durationchange", onDurationChange);
    video.addEventListener("loadedmetadata", onLoadedMetadata);
    video.addEventListener("volumechange", onVolumeChange);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("webkitfullscreenchange", onFullscreenChange);

    return () => {
      video.removeEventListener("canplay", onCanPlay);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("durationchange", onDurationChange);
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
      video.removeEventListener("volumechange", onVolumeChange);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("webkitfullscreenchange", onFullscreenChange);
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, []);

  const revealControls = useCallback(() => {
    setPlayerState((prev) => ({ ...prev, showControls: true }));
    scheduleHideControls();
  }, [scheduleHideControls]);

  return {
    playerState,
    videoRef,
    togglePlay,
    seek,
    setVolume,
    toggleMute,
    setPlaybackRate,
    toggleFullscreen,
    handleMouseMove,
    skipSeconds,
    revealControls,
  };
}
