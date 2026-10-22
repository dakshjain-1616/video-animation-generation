import { makeRng, range } from "./rng";

/**
 * Hand-inked path helpers.
 *
 * The reference line work is uniform in weight but slightly irregular in shape.
 * Rather than fake that with a displacement filter (slow, non-deterministic
 * across engines), we jitter the control points from a fixed seed.
 */

export type Point = { x: number; y: number };

export function jitterPoints(points: Point[], seed: number, amount: number): Point[] {
  const rng = makeRng(seed);
  return points.map((p) => ({
    x: p.x + range(rng, -amount, amount),
    y: p.y + range(rng, -amount, amount),
  }));
}

/**
 * Smooth path through points using quadratic midpoints. Produces the soft,
 * drawn-by-hand curve used for waves and organic outlines.
 */
export function smoothPath(points: Point[], tension = 0.5): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) {
    return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;
  }

  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const current = points[i];
    const next = points[i + 1];
    const midX = current.x + (next.x - current.x) * tension;
    const midY = current.y + (next.y - current.y) * tension;
    d += ` Q ${current.x} ${current.y} ${midX} ${midY}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

/** Reference-style travelling wave: a sine with two harmonics and a slow drift. */
export function wavePoints(options: {
  width: number;
  amplitude: number;
  cycles: number;
  samples?: number;
  seed?: number;
  wobble?: number;
  phase?: number;
}): Point[] {
  const {
    width,
    amplitude,
    cycles,
    samples = 240,
    seed = 7,
    wobble = 0.18,
    phase = 0,
  } = options;
  const rng = makeRng(seed);
  const drift = range(rng, 0, Math.PI * 2);
  const points: Point[] = [];
  for (let i = 0; i <= samples; i += 1) {
    const t = i / samples;
    const x = t * width;
    const base = Math.sin(t * Math.PI * 2 * cycles + phase);
    const harmonic = Math.sin(t * Math.PI * 2 * cycles * 2.17 + phase * 1.3 + drift) * 0.22;
    const third = Math.sin(t * Math.PI * 2 * cycles * 0.5 + drift) * 0.12;
    const y = -amplitude * (base + harmonic * wobble + third * wobble);
    points.push({ x, y });
  }
  return points;
}
