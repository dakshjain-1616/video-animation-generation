import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * Persistent section marker: an orange rule, the chapter number in accent, and
 * the chapter name in muted ink. Sits top-left on long cuts; short cuts use a
 * single topic label instead (see `TopicTag`).
 */
export const SectionHeader = ({
  index,
  title,
  x,
  y,
  delay = 0,
  showNumber = true,
}: {
  index?: string;
  title: string;
  x: number;
  y: number;
  delay?: number;
  showNumber?: boolean;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const rule = enterProgress(frame, fps, delay, 0.5);
  const text = enterProgress(frame, fps, delay + 0.12, 0.5);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        display: "flex",
        alignItems: "center",
        gap: 18,
        fontFamily: pack.fonts.mono,
        fontSize: pack.type.label.md,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        lineHeight: 1,
        whiteSpace: "nowrap",
      }}
    >
      <div
        style={{
          width: 46 * rule,
          height: 3,
          backgroundColor: colors.accent,
          borderRadius: 2,
        }}
      />
      <div style={{ opacity: text, display: "flex", gap: 14 }}>
        {showNumber && index ? <span style={{ color: colors.accent }}>{index}</span> : null}
        <span style={{ color: colors.sub }}>{title}</span>
      </div>
    </div>
  );
};
