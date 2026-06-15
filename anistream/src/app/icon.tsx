import { ImageResponse } from "next/og";

export const runtime = "edge";
export const contentType = "image/png";

export function generateImageMetadata() {
  return [
    { id: "192", size: { width: 192, height: 192 }, contentType: "image/png" },
    { id: "512", size: { width: 512, height: 512 }, contentType: "image/png" },
  ];
}

export default function Icon({ id }: { id: string }) {
  const px = id === "192" ? 192 : 512;
  return new ImageResponse(
    (
      <div
        style={{
          width: px,
          height: px,
          background: "#0a0a0a",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width={px * 0.9} height={px * 0.9} viewBox="0 0 512 512">
          <circle cx="256" cy="256" r="256" fill="#F47521" />
          <circle cx="256" cy="256" r="128" fill="none" stroke="white" strokeWidth="48" />
          <circle cx="256" cy="256" r="55" fill="white" />
        </svg>
      </div>
    ),
    { width: px, height: px }
  );
}
