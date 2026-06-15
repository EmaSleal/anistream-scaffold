import { SignInButton } from "./SignInButton";
import styles from "./LandingCTA.module.css";

export function LandingCTA() {
  return (
    <section id="catalog-cta" className={styles.section}>
      <div className={styles.glow} aria-hidden="true" />
      <div className={styles.content}>
        <h2 className={styles.title}>Start Watching Free</h2>
        <p className={styles.subtitle}>
          No credit card required. Sign in with Google to unlock your watchlist.
        </p>
        <div className={styles.actions}>
          <SignInButton
            variant="primary"
            label="Continue with Google — It's Free"
          />
          <SignInButton
            variant="secondary"
            label="Already have an account? Sign In"
          />
        </div>
      </div>
    </section>
  );
}
