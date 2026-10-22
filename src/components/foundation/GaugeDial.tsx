import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress, easeOutExpo, clamp01 } from "../../lib/motion";

/**
 * GaugeDial: a semicircular gauge with a needle that swings to the value —
 * for rates, risk levels, confidence, share. Value snaps to [0, 1]; the
 * needle uses the composition fps so it behaves the same at 30 and 60.
 */
export const GaugeDial = ({
  value,
  x,
  y,
  size = 360,
  label,
  delay = 0,
  duration = 1.1,
}: {
  /** Target position of the needle, 0..1 (left to right). */
  value: number;
  x: number;
  y: number;
  size?: number;
  label?: string;
  delay?: number;
  duration?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const enter = enterProgress(frame, fps, delay, 0.4);
  const clamped = Math.min(1, Math.max(0, value));
  const swing = easeOutExpo(clamp01((frame - delay * fps) / Math.max(1, duration * fps)));

  const radius = size / 2 - 12;
  const cx = size / 2;
  const cy = size / 2;
  // Needle sweeps from the left end (theta = PI) to the value's position.
  const theta = Math.PI * (1 - clamped * swing);
  const needle = {
    x: cx + Math.cos(theta) * radius * 0.9,
    y: cy - Math.sin(theta) * radius * 0.9,
  };

  // Arc from left (180 deg) to right (0 deg).
  const arc = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;
  // Filled portion of the arc up to the value.
  const filled = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + Math.cos(Math.PI - Math.PI * clamped) * radius} ${cy - Math.sin(Math.PI * clamped) * radius}`;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: size,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 10}px)`,
      }}
    >
      <svg width={size} height={size * 0.62} viewBox={`0 0 ${size} ${size * 0.62}`} fill="none">
        <path
          d={arc}
          stroke={colors.sub}
          strokeWidth={pack.stroke.hair + 2}
          strokeLinecap="round"
          opacity={0.45}
        />
        <path
          d={filled}
          stroke={colors.accent}
          strokeWidth={pack.stroke.regular}
          strokeLinecap="round"
          pathLength={1}
          style={{ strokeDasharray: 1, strokeDashoffset: 1 - enterProgress(frame, fps, delay, duration) }}
        />
        <line
          x1={cx}
          y1={cy}
          x2={needle.x}
          y2={needle.y}
          stroke={colors.fg}
          strokeWidth={pack.stroke.hair + 2}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={7} fill={colors.fg} />
      </svg>
      {label ? (
        <div
          style={{
            marginTop: 8,
            textAlign: "center",
            fontFamily: pack.fonts.mono,
            fontSize: pack.type.label.md,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: colors.sub,
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
};
