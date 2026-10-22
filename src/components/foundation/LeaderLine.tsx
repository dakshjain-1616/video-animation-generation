import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import type { Point } from "../../lib/ink";

/**
 * Leader line with a mono label. The line draws from the label toward the
 * target and ends in a dot, so the annotation reads as "this, specifically".
 *
 * `labelAt` is the anchor on the label's inner edge (left/right for horizontal
 * leaders, centered top/bottom for vertical ones); `target` is the exact point
 * in the frame, never an eyeballed coordinate.
 */
export const LeaderLine = ({
  label,
  labelAt,
  target,
  side,
  delay = 0,
  duration = 0.5,
  color,
  labelColor,
  size = "md",
  dot = true,
  dash = false,
}: {
  label: string;
  labelAt: Point;
  target: Point;
  side: "left" | "right" | "up" | "down";
  delay?: number;
  duration?: number;
  color?: string;
  labelColor?: string;
  size?: "lg" | "md" | "sm";
  dot?: boolean;
  dash?: boolean;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const lineColor = resolveColor(color, colors, colors.sub) ?? colors.sub;
  const horizontal = side === "left" || side === "right";
  const sign = side === "right" || side === "down" ? 1 : -1;

  // The label is anchored on its inner edge, so the rule can start there. The
  // elbow is a short stub in the label's direction, then an S-curve into the
  // target's approach point, so horizontal and vertical leaders feel the same.
  const start: Point = labelAt;
  const elbow1: Point = horizontal
    ? { x: start.x + sign * 10, y: start.y }
    : { x: start.x, y: start.y + sign * 10 };
  const approach = horizontal ? (side === "left" ? -26 : 26) : side === "up" ? -26 : 26;
  const elbow2: Point = horizontal
    ? { x: target.x + approach, y: target.y }
    : { x: target.x, y: target.y + approach };
  const midX = (elbow1.x + elbow2.x) / 2;
  const midY = (elbow1.y + elbow2.y) / 2;
  const bend1 = horizontal ? elbow1.x : elbow1.y;
  const bend2 = horizontal ? elbow2.x : elbow2.y;
  const path = horizontal
    ? `M ${start.x} ${start.y} L ${elbow1.x} ${elbow1.y} Q ${elbow1.x} ${midY} ${midX} ${midY} Q ${elbow2.x} ${midY} ${elbow2.x} ${elbow2.y} L ${target.x} ${target.y}`
    : `M ${start.x} ${start.y} L ${elbow1.x} ${elbow1.y} Q ${elbow1.x} ${bend1} ${midX} ${midY} Q ${elbow2.x} ${bend2} ${elbow2.x} ${elbow2.y} L ${target.x} ${target.y}`;

  const lineProgress = enterProgress(frame, fps, delay, duration);
  const labelProgress = enterProgress(frame, fps, delay + duration * 0.55, 0.4);

  return (
    <>
      <svg
        width="100%"
        height="100%"
        style={{ position: "absolute", inset: 0, overflow: "visible" }}
      >
        <path
          d={path}
          fill="none"
          stroke={lineColor}
          strokeWidth={pack.stroke.hair}
          strokeLinecap="round"
          strokeDasharray={dash ? "6 7" : "1"}
          pathLength={dash ? undefined : 1}
          strokeDashoffset={dash ? undefined : 1 - lineProgress}
          opacity={dash ? lineProgress * 0.9 : 1}
        />
        {dot ? (
          <circle
            cx={target.x}
            cy={target.y}
            r={5}
            fill={colors.accent}
            opacity={lineProgress > 0.92 ? 1 : 0}
          />
        ) : null}
      </svg>
      <div
        style={{
          position: "absolute",
          left: labelAt.x,
          top: labelAt.y,
          transform: `translate(${labelShiftX(side)}, ${labelShiftY(side)}) translateY(${
            (1 - labelProgress) * 6
          }px)`,
          opacity: labelProgress,
          fontFamily: pack.fonts.mono,
          fontSize: pack.type.label[size],
          fontWeight: 500,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: labelColor ?? colors.fg,
          whiteSpace: "nowrap",
          lineHeight: 1,
        }}
      >
        {label}
      </div>
    </>
  );
};

const labelShiftX = (side: "left" | "right" | "up" | "down"): string =>
  side === "left" ? "-100%" : side === "right" ? "0" : "-50%";

const labelShiftY = (side: "left" | "right" | "up" | "down"): string =>
  side === "up" ? "-100%" : side === "down" ? "0" : "-50%";
