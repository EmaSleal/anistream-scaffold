import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Anistream — Watch Anime Free";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 1200,
          height: 630,
          background: "#0a0a0a",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: 24,
            padding: "0 100px",
          }}
        >
          {/* Logo row */}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <svg width="64" height="64" viewBox="0 0 28 28">
              <circle cx="14" cy="14" r="14" fill="#F47521" />
              <circle cx="14" cy="14" r="7" fill="none" stroke="white" strokeWidth="3" />
              <circle cx="14" cy="14" r="3" fill="white" />
            </svg>
            <span
              style={{
                fontSize: 36,
                fontWeight: 800,
                color: "#fff",
                letterSpacing: "-0.02em",
              }}
            >
              anistream
            </span>
          </div>
          {/* Heading */}
          <div
            style={{
              fontSize: 72,
              fontWeight: 800,
              color: "#fff",
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
            }}
          >
            Watch Anime Free
          </div>
          {/* Sub-line */}
          <div
            style={{
              fontSize: 28,
              color: "rgba(255,255,255,0.55)",
              fontWeight: 400,
            }}
          >
            Simulcasts · Sub &amp; Dub · Free Forever
          </div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 }
  );
}
