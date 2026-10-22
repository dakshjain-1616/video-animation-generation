import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * Hand-inked arrow, drawn on from its tail.
 *
 * Horizontal arrows use x as the tail and y as the centerline. Vertical arrows
 * use y as the tail and x as the centerline, so a downward arrow starts at
 * (x, y) and grows toward (x, y + length).
 */
export const Arrow = ({
  x,
  y,
  length,
  color,
  thickness,
  delay = 0,
  duration = 0.45,
  direction = "right",
}: {
  x: number;
  y: number;
  length: number;
  color?: string;
  thickness?: number;
  delay?: number;
  duration?: number;
  direction?: "right" | "left" | "up" | "down";
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const progress = enterProgress(frame, fps, delay, duration);
  const head = 18;
  const stroke = thickness ?? pack.stroke.regular;
  const end = length * progress;
  const vertical = direction === "up" || direction === "down";
  const center = head + stroke / 2;
  const width = vertical ? head * 2 + stroke : length + 2;
  const height = vertical ? length + 2 : head * 2 + stroke;

  const tip =
    direction === "down"
      ? { x: center, y: end }
      : direction === "up"
        ? { x: center, y: length - end }
        : direction === "left"
          ? { x: length - end, y: center }
          : { x: end, y: center };
  const tail =
    direction === "down"
      ? { x: center, y: 0 }
      : direction === "up"
        ? { x: center, y: length }
        : direction === "left"
          ? { x: length, y: center }
          : { x: 0, y: center };
  // Barbs sit behind the tip along the arrow's axis, one on each side.
  const along = direction === "right" || direction === "down" ? -head : head;
  const leftBarb = vertical
    ? { x: tip.x - head, y: tip.y + along }
    : { x: tip.x + along, y: tip.y - head };
  const rightBarb = vertical
    ? { x: tip.x + head, y: tip.y + along }
    : { x: tip.x + along, y: tip.y + head };

  return (
    <svg
      width={width}
      height={height}
      style={{
        position: "absolute",
        left: vertical ? x - center : x,
        top: vertical ? y : y - center,
        overflow: "visible",
      }}
    >
      <g
        stroke={resolveColor(color, colors, colors.accent)}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      >
        <path d={`M ${tail.x} ${tail.y} L ${tip.x} ${tip.y}`} />
        {progress > 0.85 ? (
          <path d={`M ${leftBarb.x} ${leftBarb.y} L ${tip.x} ${tip.y} L ${rightBarb.x} ${rightBarb.y}`} />
        ) : null}
      </g>
    </svg>
  );
};
