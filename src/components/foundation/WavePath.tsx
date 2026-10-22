import { useMemo } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { wavePoints, smoothPath } from "../../lib/ink";

/**
 * A drawn-on wave. Used for sound, radio, and pressure graphs. The draw-on is
 * driven by `pathLength`, so line weight stays constant along the stroke.
 *
 * Negative or zero amplitudes are legal: a negative amplitude is an inverted
 * wave (used for anti-noise), zero is a flat line (used for cancellation).
 *
 * `y` is always the wave's centerline, whatever the amplitude. This is what
 * lets an original wave, its inverse and their flat sum share one y.
 */
export const WavePath = ({
  x,
  y,
  width,
  amplitude,
  cycles = 3,
  color,
  strokeWidth,
  delay = 0,
  duration = 0.7,
  seed = 5,
  phase = 0,
  opacity = 1,
}: {
  x: number;
  y: number;
  width: number;
  amplitude: number;
  cycles?: number;
  color?: string;
  strokeWidth?: number;
  delay?: number;
  duration?: number;
  seed?: number;
  phase?: number;
  opacity?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const progress = enterProgress(frame, fps, delay, duration);

  const d = useMemo(() => {
    const points = wavePoints({ width, amplitude, cycles, seed, phase });
    return smoothPath(points);
  }, [width, amplitude, cycles, seed, phase]);

  const height = Math.max(2, Math.abs(amplitude) * 2.4);
  const baseline = height / 2;

  return (
    <svg
      x={x}
      y={y - baseline}
      width={width}
      height={height}
      style={{ position: "absolute", left: x, top: y - baseline, overflow: "visible" }}
    >
      <g transform={`translate(0, ${baseline})`}>
        <path
          d={d}
          fill="none"
          stroke={resolveColor(color, colors, colors.fg)}
          strokeWidth={strokeWidth ?? pack.stroke.regular}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - progress}
          opacity={opacity}
        />
      </g>
    </svg>
  );
};
