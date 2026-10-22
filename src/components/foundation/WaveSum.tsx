import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { MonoLabel } from "./MonoLabel";
import { WavePath } from "./WavePath";

/**
 * WaveSum: the "two waves cancel" composition, correct by construction.
 *
 * The original, its inverse and the flat sum all share one centerline, which
 * is the part free-form scene code kept getting wrong. The two sources settle
 * back as the result line draws, so the viewer reads "these add to nothing"
 * rather than "here are three unrelated lines".
 */
export const WaveSum = ({
  x,
  y,
  width,
  amplitude = 80,
  cycles = 3,
  delay = 0,
  duration = 2.0,
  seed = 5,
  resultLabel,
}: {
  x: number;
  /** Centerline shared by both waves and the result. */
  y: number;
  width: number;
  amplitude?: number;
  cycles?: number;
  delay?: number;
  duration?: number;
  seed?: number;
  /** Optional short label for the resultant line, e.g. "SUM: SILENCE". */
  resultLabel?: string;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack } = useTheme();
  const settleFrom = (delay + duration * 0.6) * fps;
  const settleTo = (delay + duration) * fps;
  const settle = interpolate(frame, [settleFrom, settleTo], [1, 0.3], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const resultDelay = delay + duration * 0.65;

  return (
    <>
      <WavePath
        x={x}
        y={y}
        width={width}
        amplitude={amplitude}
        cycles={cycles}
        color="ink"
        delay={delay}
        duration={duration * 0.55}
        seed={seed}
        opacity={settle}
      />
      <WavePath
        x={x}
        y={y}
        width={width}
        amplitude={-amplitude}
        cycles={cycles}
        color="accent"
        delay={delay + duration * 0.2}
        duration={duration * 0.55}
        seed={seed}
        opacity={settle}
      />
      <WavePath
        x={x}
        y={y}
        width={width}
        amplitude={0}
        cycles={cycles}
        color="accent"
        strokeWidth={pack.stroke.heavy}
        delay={resultDelay}
        duration={duration * 0.3}
      />
      {resultLabel ? (
        <MonoLabel
          x={x + width}
          y={y - Math.max(28, Math.abs(amplitude) * 0.9)}
          size="sm"
          color="accent"
          align="right"
          delay={resultDelay}
        >
          {resultLabel}
        </MonoLabel>
      ) : null}
    </>
  );
};
