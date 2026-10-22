import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * HeadlineCard: a themed news headline, quoted verbatim from the brief.
 * Outlet in mono on top, big display headline, optional provenance line.
 */
export const HeadlineCard = ({
  outlet,
  headline,
  time,
  x,
  y,
  width,
  delay = 0,
}: {
  outlet: string;
  headline: string;
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
  const heading = enterProgress(frame, fps, delay + 0.14, 0.6);
  const rule = enterProgress(frame, fps, delay + 0.3, 0.5);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        padding: "26px 28px",
        background: pack.palette.chalk,
        border: `${pack.stroke.hair}px solid ${pack.palette.ink}`,
        borderLeft: `${pack.stroke.regular}px solid ${pack.palette.accent}`,
        boxShadow: "8px 10px 0 rgba(0,0,0,0.18)",
        opacity: enter,
        transform: `rotate(-0.8deg) translateY(${(1 - enter) * 12}px)`,
      }}
    >
      <div
        style={{
          fontFamily: pack.fonts.mono,
          fontSize: pack.type.label.sm,
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: pack.palette.muted,
        }}
      >
        {outlet}
        {time ? ` · ${time}` : ""}
      </div>
      <div
        style={{
          marginTop: 14,
          fontFamily: pack.fonts.display,
          fontSize: pack.type.display.md,
          lineHeight: 1.0,
          textTransform: "uppercase",
          color: pack.palette.ink,
          opacity: heading,
          transform: `translateY(${(1 - heading) * 10}px)`,
        }}
      >
        {headline}
      </div>
      <div
        style={{
          height: 3,
          width: 140 * rule,
          background: pack.palette.accent,
          marginTop: 20,
          opacity: rule,
        }}
      />
    </div>
  );
};
