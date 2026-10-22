import { useMemo } from "react";
import { resolveColor, useTheme } from "../../lib/theme";
import { makeRng, range } from "../../lib/rng";

type Particle = { x: number; y: number; r: number; alpha: number };

/**
 * Particle field used for air / signal / packet visuals.
 *
 * `compression` (0..1) pulls particles into vertical bands, the way the
 * reference shows pressure waves moving through open air. Particles are stable
 * across frames: only their displacement is animated, never their identity.
 */
export const DotField = ({
  x,
  y,
  width,
  height,
  count = 1400,
  seed = 3,
  compression = 0,
  wavelength = 240,
  color,
  opacity = 1,
  radius = [1.4, 2.8] as [number, number],
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  count?: number;
  seed?: number;
  compression?: number;
  wavelength?: number;
  color?: string;
  opacity?: number;
  /** Particle radius: a [min, max] range, or one number for a uniform size. */
  radius?: number | [number, number];
}) => {
  const { colors } = useTheme();
  const [rMin, rMax] = typeof radius === "number" ? [radius, radius] : radius;

  const particles = useMemo<Particle[]>(() => {
    const rng = makeRng(seed);
    return Array.from({ length: count }, () => ({
      x: range(rng, 0, width),
      y: range(rng, 0, height),
      r: range(rng, rMin, rMax),
      alpha: range(rng, 0.72, 1),
    }));
  }, [count, seed, width, height, rMin, rMax]);

  const bandStrength = (px: number) => {
    const phase = (px / wavelength) * Math.PI * 2;
    // Peaks of this sine are the dense columns.
    return Math.pow(Math.max(0, Math.sin(phase)), 1.6);
  };

  return (
    <svg
      width={width}
      height={height}
      style={{ position: "absolute", left: x, top: y, overflow: "visible" }}
    >
      {particles.map((p, i) => {
        const band = bandStrength(p.x);
        const shift = compression * band * (wavelength * 0.16);
        return (
          <circle
            key={i}
            cx={p.x + shift}
            cy={p.y}
            r={p.r * (1 + compression * band * 0.25)}
            fill={resolveColor(color, colors, colors.fg)}
            opacity={opacity * p.alpha * (0.72 + compression * band * 0.5)}
          />
        );
      })}
    </svg>
  );
};
