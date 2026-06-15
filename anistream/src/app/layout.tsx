import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ErudaDebug } from "@/components/debug/ErudaDebug";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "Anistream", template: "%s | Anistream" },
  description: "Watch the best anime, anytime, anywhere.",
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          {children}
          <Suspense>
            <ErudaDebug />
          </Suspense>
        </AuthProvider>
      </body>
    </html>
  );
}
