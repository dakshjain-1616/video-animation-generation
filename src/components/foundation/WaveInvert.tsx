import { useCurrentFrame, useVideoConfig } from "remotion";
import { enterProgress } from "../../lib/motion";
import { Arrow } from "./Arrow";
import { MonoLabel } from "./MonoLabel";
import { WavePath } from "./WavePath";

/**
 * WaveInvert: an original wave and its exact mirror, side by side.
 *
 * Free-form code kept drawing two identical sine plots and calling one
 * "inverted". Here both traces share one seed, centerline and cycle count; the
 * right trace is the negative amplitude, so every peak sits where the left
 * trace has a trough by construction.
 */
export const WaveInvert = ({
  x,
  y,
  width,
  amplitude = 90,
  cycles = 3,
  gap = 72,
  leftLabel = "HEARD",
  rightLabel = "INVERTED",
  delay = 0,
  duration = 1.8,
  seed = 5,
}: {
  x: number;
  /** Shared centerline for both traces. */
  y: number;
  width: number;
  amplitude?: number;
  cycles?: number;
  gap?: number;
  leftLabel?: string;
  rightLabel?: string;
  delay?: number;
  duration?: number;
  seed?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const trace = Math.max(80, (width - gap) / 2);
  const rightX = x + trace + gap;
  const labelY = y - Math.abs(amplitude) - 34;
  const arrowProgress = enterProgress(frame, fps, delay + duration * 0.5, 0.5);

  return (
    <>
      <MonoLabel x={x} y={labelY} size="sm" color="sub" delay={delay}>
        {leftLabel}
      </MonoLabel>
      <MonoLabel x={rightX} y={labelY} size="sm" color="accent" delay={delay + duration * 0.25}>
        {rightLabel}
      </MonoLabel>
      <WavePath
        x={x}
        y={y}
        width={trace}
        amplitude={amplitude}
        cycles={cycles}
        color="ink"
        delay={delay}
        duration={duration * 0.6}
        seed={seed}
      />
      <WavePath
        x={rightX}
        y={y}
        width={trace}
        amplitude={-amplitude}
        cycles={cycles}
        color="accent"
        delay={delay + duration * 0.25}
        duration={duration * 0.6}
        seed={seed}
      />
      {arrowProgress > 0 ? (
        <Arrow
          x={x + trace + 8}
          y={y}
          length={Math.max(8, gap - 16) * arrowProgress}
          color="sub"
          thickness={3}
          delay={delay + duration * 0.45}
          direction="right"
        />
      ) : null}
    </>
  );
};
