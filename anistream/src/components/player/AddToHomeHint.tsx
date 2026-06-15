"use client";

import styles from "./AddToHomeHint.module.css";

interface AddToHomeHintProps {
  onDismiss: () => void;
}

export function AddToHomeHint({ onDismiss }: AddToHomeHintProps) {
  return (
    <div className={styles.backdrop} onClick={onDismiss}>
      <div className={styles.sheet} onClick={(e) => e.stopPropagation()}>
        <button className={styles.close} onClick={onDismiss} aria-label="Dismiss">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className={styles.icon}>
          <svg width="32" height="32" viewBox="0 0 28 28" aria-hidden="true">
            <circle cx="14" cy="14" r="14" fill="#F47521" />
            <circle cx="14" cy="14" r="7" fill="none" stroke="white" strokeWidth="3" />
            <circle cx="14" cy="14" r="3" fill="white" />
          </svg>
        </div>

        <h2 className={styles.title}>Enable Fullscreen</h2>
        <p className={styles.subtitle}>Add Anistream to your Home Screen to watch in true fullscreen.</p>

        <ol className={styles.steps}>
          <li className={styles.step}>
            <span className={styles.stepIcon}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
                <polyline points="16 6 12 2 8 6" />
                <line x1="12" y1="2" x2="12" y2="15" />
              </svg>
            </span>
            Tap the <strong>Share</strong> button in Safari
          </li>
          <li className={styles.step}>
            <span className={styles.stepIcon}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <path d="M14 17h3m0 0h3m-3 0v-3m0 3v3" />
              </svg>
            </span>
            Select <strong>Add to Home Screen</strong>
          </li>
          <li className={styles.step}>
            <span className={styles.stepIcon}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
            Open Anistream from your Home Screen
          </li>
        </ol>

        <button className={styles.dismiss} onClick={onDismiss}>Got it</button>
      </div>
    </div>
  );
}
