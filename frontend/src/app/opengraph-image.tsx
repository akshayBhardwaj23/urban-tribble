import { ImageResponse } from "next/og";
import { META_DESCRIPTION, PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/brand";

export const alt = `${PRODUCT_NAME} - AI business analyst for spreadsheets`;
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          alignItems: "center",
          background:
            "linear-gradient(135deg, #f6f4ef 0%, #ffffff 42%, #ede7ff 100%)",
          color: "#0f172a",
          display: "flex",
          fontFamily: "Inter, Arial, sans-serif",
          height: "100%",
          justifyContent: "center",
          padding: 64,
          width: "100%",
        }}
      >
        <div
          style={{
            background: "rgba(255, 255, 255, 0.82)",
            border: "1px solid rgba(15, 23, 42, 0.10)",
            borderRadius: 48,
            boxShadow: "0 36px 90px rgba(79, 70, 229, 0.18)",
            display: "flex",
            flexDirection: "column",
            gap: 28,
            padding: 56,
            width: "100%",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div
              style={{
                background: "#4f46e5",
                borderRadius: 24,
                color: "#ffffff",
                display: "flex",
                fontSize: 30,
                fontWeight: 800,
                height: 72,
                letterSpacing: "-0.04em",
                lineHeight: "72px",
                textAlign: "center",
                width: 72,
              }}
            >
              S
            </div>
            <div
              style={{
                color: "#4f46e5",
                display: "flex",
                fontSize: 24,
                fontWeight: 700,
                letterSpacing: "-0.02em",
              }}
            >
              {PRODUCT_NAME}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 24,
              maxWidth: 900,
            }}
          >
            <div
              style={{
                color: "#111827",
                display: "flex",
                fontSize: 76,
                fontWeight: 800,
                letterSpacing: "-0.055em",
                lineHeight: 0.95,
              }}
            >
              Turn spreadsheets into confident decisions.
            </div>
            <div
              style={{
                color: "#475569",
                display: "flex",
                fontSize: 30,
                fontWeight: 500,
                lineHeight: 1.35,
                maxWidth: 840,
              }}
            >
              {PRODUCT_TAGLINE} {META_DESCRIPTION}
            </div>
          </div>
        </div>
      </div>
    ),
    size,
  );
}
