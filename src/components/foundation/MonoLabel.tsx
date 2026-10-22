import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * Micro-label: uppercase mono with wide tracking — the reference's annotation
 * voice. Critical text never uses this size; it is for labels only.
 */
export const MonoLabel = ({
  children,
  x,
  y,
  size = "md",
  color,
  align = "left",
  delay = 0,
  duration = 0.45,
  tracking = 0.18,
  weight = 500,
}: {
  children: string;
  x: number;
  y: number;
  size?: "lg" | "md" | "sm";
  color?: string;
  align?: "left" | "center" | "right";
  delay?: number;
  duration?: number;
  tracking?: number;
  weight?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const progress = enterProgress(frame, fps, delay, duration);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `translate(${align === "center" ? "-50%" : align === "right" ? "-100%" : "0"}, -50%) translateY(${
          (1 - progress) * 8
        }px)`,
        opacity: progress,
        fontFamily: pack.fonts.mono,
        fontSize: pack.type.label[size],
        fontWeight: weight,
        letterSpacing: `${tracking}em`,
        textTransform: "uppercase",
        color: resolveColor(color, colors, colors.sub),
        whiteSpace: "nowrap",
        lineHeight: 1,
      }}
    >
      {children}
    </div>
  );
};
