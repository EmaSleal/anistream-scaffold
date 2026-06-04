import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import styles from "./Badge.module.css";

interface BadgeProps {
  children: ReactNode;
  variant?: "rating" | "format" | "brand" | "seen";
  className?: string;
}

export function Badge({ children, variant = "rating", className }: BadgeProps) {
  return (
    <span className={cn(styles.badge, styles[variant], className)}>
      {children}
    </span>
  );
}
