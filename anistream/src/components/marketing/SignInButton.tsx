"use client";

import { signIn } from "next-auth/react";
import styles from "./LandingCTA.module.css";

interface SignInButtonProps {
  variant?: "primary" | "secondary";
  label: string;
}

export function SignInButton({ variant = "primary", label }: SignInButtonProps) {
  return (
    <button
      type="button"
      className={variant === "primary" ? styles.primaryBtn : styles.secondaryBtn}
      onClick={() => signIn("google")}
    >
      {label}
    </button>
  );
}
