/**
 * Deterministic pseudo-randomness.
 *
 * Every scatter, jitter and wobble in the render must be reproducible, so all
 * randomness flows through a seeded generator. Never call Math.random().
 */

export type Rng = () => number;

/** mulberry32 — small, fast, good enough for visual scatter. */
export function makeRng(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable string hash, used to derive per-scene seeds from scene ids. */
export function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function range(rng: Rng, min: number, max: number): number {
  return min + rng() * (max - min);
}
