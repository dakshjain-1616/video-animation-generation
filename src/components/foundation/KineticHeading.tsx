import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { estimateTextWidth } from "../../lib/layout";
import { useStage } from "../../lib/stage";

/**
 * Display heading with a per-line mask reveal. Lines rise out of a clip mask,
 * which reads as a deliberate editorial cut rather than a fade. The type size
 * is fitted to the stage so long lines never leave the safe area.
 */
export const KineticHeading = ({
  lines,
  x,
  y,
  size = "lg",
  color,
  align = "left",
  delay = 0,
  stagger = 0.1,
  duration = 0.6,
  highlight,
}: {
  lines: string[];
  x: number;
  y: number;
  size?: "xl" | "lg" | "md";
  color?: string;
  align?: "left" | "center" | "right";
  delay?: number;
  stagger?: number;
  duration?: number;
  /** Line indexes rendered in the accent color. */
  highlight?: number[];
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const stage = useStage();
  // Shrink, never clip: the widest line must fit between its anchor and the
  // safe edge, so the same copy works in 16:9 and 9:16.
  const room =
    align === "center"
      ? Math.min(x - stage.left, stage.right - x) * 2
      : align === "right"
        ? x - stage.left
        : stage.right - x;
  const widest = Math.max(...lines.map((line) => estimateTextWidth(line, 1, -0.015, "display")));
  const fontSize = Math.floor(Math.min(pack.type.display[size], room / widest));
  const highlighted = new Set(highlight ?? []);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: "auto",
        transform: `translate(${align === "center" ? "-50%" : align === "right" ? "-100%" : "0"}, 0)`,
        textAlign: align,
      }}
    >
      {lines.map((line, i) => {
        const progress = enterProgress(frame, fps, delay + i * stagger, duration);
        return (
          <div
            key={line}
            style={{
              overflow: "hidden",
              paddingBottom: fontSize * 0.06,
              marginBottom: -fontSize * 0.06,
            }}
          >
            <div
              style={{
                fontFamily: pack.fonts.display,
                fontSize,
                lineHeight: 0.9,
                letterSpacing: "-0.015em",
                textTransform: "uppercase",
                color: highlighted.has(i) ? colors.accent : resolveColor(color, colors, colors.fg),
                transform: `translateY(${(1 - progress) * 108}%)`,
                whiteSpace: "nowrap",
              }}
            >
              {line}
            </div>
          </div>
        );
      })}
    </div>
  );
};
