import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 180,
          height: 180,
          background: "#0a0a0a",
          borderRadius: 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="150" height="150" viewBox="0 0 512 512">
          <circle cx="256" cy="256" r="256" fill="#F47521" />
          <circle cx="256" cy="256" r="128" fill="none" stroke="white" strokeWidth="48" />
          <circle cx="256" cy="256" r="55" fill="white" />
        </svg>
      </div>
    ),
    { width: 180, height: 180 }
  );
}
