"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Episode } from "@/types";
import { usePlayerControls } from "@/hooks/usePlayerControls";
import { saveWatchProgress, advanceToNextEpisode } from "@/app/actions/watchProgress";
import { PlayerControls } from "./PlayerControls";
import { MobilePlayerControls } from "./MobilePlayerControls";
import { EpisodeCard } from "@/components/shared/EpisodeCard";
import { Badge } from "@/components/ui/Badge";
import { formatEpisodeLabel } from "@/lib/utils";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  episode: Episode;
  previousEpisode?: Episode;
  nextEpisode?: Episode;
  initialProgress?: number;
  streamUrl?: string;
  streamType?: "mp4" | "hls";
}

export function VideoPlayer({
  episode,
  previousEpisode,
  nextEpisode,
  initialProgress = 0,
  streamUrl,
  streamType = "mp4",
}: VideoPlayerProps) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const hasTriggered = useRef<boolean>(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const {
    playerState,
    videoRef,
    togglePlay,
    seek,
    skipSeconds,
    setVolume,
    toggleMute,
    setPlaybackRate,
    toggleFullscreen,
    handleMouseMove,
    revealControls,
  } = usePlayerControls(episode.duration, initialProgress);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      switch (e.key) {
        case " ":
        case "k":
        case "K":
          e.preventDefault();
          togglePlay();
          break;
        case "ArrowLeft":
        case "j":
        case "J":
          e.preventDefault();
          skipSeconds(-10);
          break;
        case "ArrowRight":
        case "l":
        case "L":
          e.preventDefault();
          skipSeconds(10);
          break;
        case "m":
        case "M":
          e.preventDefault();
          toggleMute();
          break;
        case "f":
        case "F":
          e.preventDefault();
          toggleFullscreen(containerRef);
          break;
        case "ArrowUp":
          e.preventDefault();
          if (videoRef.current) setVolume(Math.min(1, videoRef.current.volume + 0.1));
          break;
        case "ArrowDown":
          e.preventDefault();
          if (videoRef.current) setVolume(Math.max(0, videoRef.current.volume - 0.1));
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, skipSeconds, toggleMute, toggleFullscreen, setVolume, containerRef, videoRef]);

  const hlsRef = useRef<import("hls.js").default | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    console.log("[player] HLS effect — streamUrl:", streamUrl, "streamType:", streamType, "video:", !!video);
    if (!video || !streamUrl || streamType !== "hls") return;

    // iOS / Safari: no MSE support — set src directly so it's ready before first tap
    if (typeof window !== "undefined" && !window.MediaSource) {
      console.log("[player] iOS native HLS path — setting src directly");
      video.src = streamUrl;
      video.load();
      return () => { video.src = ""; };
    }

    // Desktop: load HLS.js asynchronously
    console.log("[player] HLS.js async path — importing...");
    let cancelled = false;
    import("hls.js").then(({ default: Hls }) => {
      if (cancelled || !videoRef.current) return;
      const supported = Hls.isSupported();
      const canPlayNative = videoRef.current.canPlayType("application/vnd.apple.mpegurl");
      console.log("[player] HLS.js loaded — isSupported:", supported, "canPlayNative:", canPlayNative);
      if (supported) {
        hlsRef.current?.destroy();
        hlsRef.current = new Hls();
        hlsRef.current.on("hlsError" as Parameters<typeof hlsRef.current.on>[0], (_evt: unknown, data: unknown) => {
          console.error("[player] HLS.js error:", data);
        });
        hlsRef.current.loadSource(streamUrl);
        hlsRef.current.attachMedia(videoRef.current);
      } else if (canPlayNative) {
        console.log("[player] falling back to native HLS via src");
        videoRef.current.src = streamUrl;
        videoRef.current.load();
      } else {
        console.warn("[player] HLS not supported on this browser");
      }
    });

    return () => {
      cancelled = true;
      hlsRef.current?.destroy();
      hlsRef.current = null;
    };
  }, [streamUrl, streamType, videoRef]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const save = () => {
      if (video.currentTime <= 0) return;
      void saveWatchProgress(
        episode.id,
        episode.seriesId,
        Math.floor(video.currentTime),
        Math.floor(video.duration || episode.duration)
      );
    };

    const interval = setInterval(() => {
      if (!video.paused) save();
    }, 15_000);

    video.addEventListener("pause", save);

    return () => {
      clearInterval(interval);
      video.removeEventListener("pause", save);
      save();
    };
  }, [episode.id, episode.seriesId, episode.duration, videoRef]);

  // Auto-advance trigger: fires on video end OR when entering the last 2 minutes
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !nextEpisode) return;

    const startCountdown = () => {
      if (hasTriggered.current) return;
      hasTriggered.current = true;
      setCountdown(5);
    };

    const handleEnded = () => {
      startCountdown();
    };

    const handleTimeUpdate = () => {
      if (
        video.duration > 0 &&
        video.currentTime >= video.duration - 120
      ) {
        startCountdown();
      }
    };

    video.addEventListener("ended", handleEnded);
    video.addEventListener("timeupdate", handleTimeUpdate);

    return () => {
      video.removeEventListener("ended", handleEnded);
      video.removeEventListener("timeupdate", handleTimeUpdate);
    };
  }, [nextEpisode, videoRef]);

  // Countdown ticker: decrement every second; navigate when it reaches 0
  useEffect(() => {
    if (countdown === null || countdown <= 0) {
      if (countdown === 0 && nextEpisode) {
        void advanceToNextEpisode(
          episode.id,
          episode.seriesId,
          Math.floor(videoRef.current?.duration ?? episode.duration),
          nextEpisode.id,
          nextEpisode.seriesId
        ).then(() => {
          router.push(`/watch/${nextEpisode.id}`);
        });
      }
      return;
    }

    const timer = setInterval(() => {
      setCountdown((prev) => (prev !== null ? prev - 1 : null));
    }, 1000);

    return () => clearInterval(timer);
  }, [countdown, nextEpisode, episode.id, episode.seriesId, episode.duration, videoRef, router]);

  const handleCancelAdvance = () => {
    setCountdown(null);
  };

  const nextEpisodeHref = nextEpisode ? `/watch/${nextEpisode.id}` : undefined;

  return (
    <div className={styles.page}>
      {/* ── Video zone ──────────────────────────────────── */}
      <div
        ref={containerRef}
        className={styles.videoWrap}
        onMouseMove={handleMouseMove}
        onClick={togglePlay}
      >
        <video
          ref={videoRef}
          className={styles.video}
          src={streamType === "hls" ? undefined : (streamUrl ?? "/sample.mp4")}
          playsInline
          preload="metadata"
          aria-label={`${episode.seriesTitle} – ${episode.title}`}
        >
          <track kind="captions" label="English" srcLang="en" default />
        </video>

        {/* Top controls (settings / fullscreen) */}
        <div className={styles.topControls}>
          <button className={styles.topBtn} aria-label="Settings">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
          <button
            className={styles.topBtn}
            onClick={(e) => { e.stopPropagation(); toggleFullscreen(containerRef); }}
            aria-label={playerState.isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
            </svg>
          </button>
        </div>

        <PlayerControls
          state={playerState}
          onTogglePlay={togglePlay}
          onSeek={seek}
          onSkip={skipSeconds}
          onToggleMute={toggleMute}
          onSetVolume={setVolume}
          onSetPlaybackRate={setPlaybackRate}
          onToggleFullscreen={() => toggleFullscreen(containerRef)}
          show={playerState.showControls}
        />

        <MobilePlayerControls
          state={playerState}
          onTogglePlay={togglePlay}
          onSkip={skipSeconds}
          onSeek={seek}
          onToggleFullscreen={() => toggleFullscreen(containerRef)}
          onRevealControls={revealControls}
          nextEpisodeHref={nextEpisodeHref}
          show={playerState.showControls}
        />

        {countdown !== null && (
          <div className={styles.autoAdvanceOverlay}>
            <p className={styles.autoAdvanceText}>
              Next episode in {countdown}s
            </p>
            <button
              className={styles.autoAdvanceCancelBtn}
              onClick={(e) => { e.stopPropagation(); handleCancelAdvance(); }}
              aria-label="Cancel auto-advance"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* ── Metadata panel ───────────────────────────────── */}
      <div className={styles.metaPanel}>
        {/* Left: episode info */}
        <div className={styles.metaLeft}>
          <Link href={`/series/${episode.seriesId}`} className={styles.seriesLink}>
            {episode.seriesTitle}
          </Link>

          <h1 className={styles.epTitle}>
            {formatEpisodeLabel(episode.episode, episode.season)} – {episode.title}
          </h1>

          <div className={styles.badges}>
            <Badge variant="rating">{episode.rating}</Badge>
            <span className={styles.dot}>·</span>
            <span className={styles.format}>Sub | Dob</span>
          </div>

          <p className={styles.releaseDate}>
            Lanzado el {new Date(episode.releasedAt).toLocaleDateString("es", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </p>

          <div className={styles.reactions}>
            <button className={styles.reactionBtn} aria-label="Like">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
                <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
              </svg>
              951
            </button>
            <button className={styles.reactionBtn} aria-label="Dislike">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
                <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
              </svg>
              2
            </button>
            <button className={styles.shareBtn} aria-label="Share">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
              </svg>
            </button>
          </div>

          <p className={styles.description}>{episode.description}</p>

          <div className={styles.audioRow}>
            <span className={styles.audioLabel}>Audio</span>
            <span className={styles.audioValue}>
              Japanese, Español (América Latina), English, Deutsch
            </span>
          </div>

          <button className={styles.seeMore}>VER MÁS</button>
        </div>

        {/* Right: sidebar episode navigation */}
        <aside className={styles.sidebar} aria-label="Episode navigation">
          {nextEpisode && (
            <div className={styles.sideSection}>
              <h2 className={styles.sideHeading}>Siguiente episodio</h2>
              <EpisodeCard ep={nextEpisode} showSeenBadge  />
            </div>
          )}
          {previousEpisode && (
            <div className={styles.sideSection}>
              <h2 className={styles.sideHeading}>Episodio anterior</h2>
              <EpisodeCard ep={previousEpisode} showSeenBadge  />
            </div>
          )}
          <Link href={`/series/${episode.seriesId}`} className={styles.moreEpsBtn}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>
              <line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
            </svg>
            VER MÁS EPISODIOS
          </Link>
        </aside>
      </div>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className={styles.footer}>
        <div>
          <p className={styles.footerBrand}>Anistream</p>
          <p className={styles.footerLegal}>© Anistream. All rights reserved.</p>
        </div>
        <button className={styles.langBtn} aria-label="Change language">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
          Español ▾
        </button>
      </footer>
    </div>
  );
}

