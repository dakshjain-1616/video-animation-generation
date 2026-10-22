/**
 * Paper grain.
 *
 * feTurbulence with a fixed seed renders identically on every run, so this is
 * deterministic without shipping a texture bitmap. The drift is a sub-pixel
 * translation on a slow cycle, which keeps the grain from looking frozen on
 * long holds without ever producing a visible "boil".
 */
export const Grain = ({
  opacity,
  seed,
  driftFrames,
  fps,
}: {
  opacity: number;
  seed: number;
  driftFrames: number;
  fps: number;
}) => {
  const phase = (driftFrames / fps) * 0.35;
  const dx = Math.sin(phase) * 1.6;
  const dy = Math.cos(phase * 0.7) * 1.6;

  return (
    <svg
      width="100%"
      height="100%"
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      aria-hidden
    >
      <filter id="paper-grain" x="0" y="0" width="100%" height="100%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.82"
          numOctaves={3}
          seed={seed}
          stitchTiles="stitch"
        />
        <feColorMatrix type="saturate" values="0" />
        <feComponentTransfer>
          <feFuncA type="linear" slope={0.55} intercept={0} />
        </feComponentTransfer>
      </filter>
      <rect
        x={-dx}
        y={-dy}
        width="100%"
        height="100%"
        filter="url(#paper-grain)"
        opacity={opacity}
        style={{ mixBlendMode: "multiply" }}
      />
    </svg>
  );
};
