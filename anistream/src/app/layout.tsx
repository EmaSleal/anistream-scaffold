import type { Metadata } from "next";
import { Navbar } from "@/components/layout/Navbar";
import { AuthProvider } from "@/components/providers/AuthProvider";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "Anistream", template: "%s | Anistream" },
  description: "Watch the best anime, anytime, anywhere.",
  robots: { index: true, follow: true },
  viewport: "width=device-width, initial-scale=1",
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
          <Navbar />
          <main>{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
