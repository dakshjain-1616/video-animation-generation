import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * TweetCard: the themed reconstruction of a post, drawn entirely in pack
 * tokens. Used when the brief supplies text but no screenshot file. Name,
 * @handle and text are quoted verbatim from the brief — the realism comes
 * from the caller's content, never from the model.
 */
export const TweetCard = ({
  handle,
  name,
  text,
  time,
  x,
  y,
  width,
  delay = 0,
}: {
  handle: string;
  name?: string;
  text: string;
  time?: string;
  x: number;
  y: number;
  width: number;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack } = useTheme();
  const enter = enterProgress(frame, fps, delay, 0.55);
  const body = enterProgress(frame, fps, delay + 0.14, 0.6);
  const initial = (name ?? handle).replace(/^@/, "").trim().charAt(0).toUpperCase() || "?";

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        padding: "28px 30px",
        background: pack.palette.chalk,
        border: `${pack.stroke.hair}px solid ${pack.palette.ink}`,
        boxShadow: "8px 10px 0 rgba(0,0,0,0.18)",
        opacity: enter,
        transform: `rotate(-1.2deg) translateY(${(1 - enter) * 12}px)`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            width: 58,
            height: 58,
            borderRadius: "50%",
            background: pack.palette.fill,
            border: `${pack.stroke.hair}px solid ${pack.palette.muted}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: pack.fonts.display,
            fontSize: pack.type.label.lg,
            color: pack.palette.ink,
          }}
        >
          {initial}
        </div>
        <div>
          <div
            style={{
              fontFamily: pack.fonts.text,
              fontWeight: 700,
              fontSize: pack.type.body.md,
              color: pack.palette.ink,
              lineHeight: 1.1,
            }}
          >
            {name ?? handle}
          </div>
          <div
            style={{
              fontFamily: pack.fonts.mono,
              fontSize: pack.type.label.sm,
              letterSpacing: "0.08em",
              color: pack.palette.muted,
              marginTop: 6,
            }}
          >
            {handle}
            {time ? ` · ${time}` : ""}
          </div>
        </div>
      </div>
      <div
        style={{
          marginTop: 22,
          fontFamily: pack.fonts.text,
          fontSize: pack.type.body.lg,
          lineHeight: 1.28,
          color: pack.palette.ink,
          opacity: body,
          transform: `translateY(${(1 - body) * 8}px)`,
        }}
      >
        {text}
      </div>
    </div>
  );
};
