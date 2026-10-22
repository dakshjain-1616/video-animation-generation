import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * Chapter card: oversized number, display title, and a rule. Used sparingly —
 * at 20-30 s the video gets at most one, and short cuts use a topic tag instead.
 */
export const ChapterCard = ({
  index,
  title,
  kicker,
  delay = 0,
}: {
  index: string;
  title: string;
  kicker?: string;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const number = enterProgress(frame, fps, delay, 0.55);
  const heading = enterProgress(frame, fps, delay + 0.12, 0.55);
  const rule = enterProgress(frame, fps, delay + 0.3, 0.6);

  return (
    <div style={{ position: "absolute", left: 160, top: 300 }}>
      <div
        style={{
          fontFamily: pack.fonts.mono,
          fontSize: pack.type.label.lg,
          letterSpacing: "0.2em",
          color: colors.accent,
          opacity: number,
          transform: `translateY(${(1 - number) * 10}px)`,
        }}
      >
        {index}
      </div>
      <div
        style={{
          fontFamily: pack.fonts.display,
          fontSize: pack.type.display.xl,
          lineHeight: 0.92,
          letterSpacing: "-0.015em",
          textTransform: "uppercase",
          color: colors.fg,
          opacity: heading,
          transform: `translateY(${(1 - heading) * 14}px)`,
          marginTop: 18,
        }}
      >
        {title}
      </div>
      <div
        style={{
          height: 3,
          width: 220 * rule,
          backgroundColor: colors.accent,
          marginTop: 34,
        }}
      />
      {kicker ? (
        <div
          style={{
            fontFamily: pack.fonts.mono,
            fontSize: pack.type.label.md,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: colors.sub,
            opacity: rule,
            marginTop: 26,
          }}
        >
          {kicker}
        </div>
      ) : null}
    </div>
  );
};
