/**
 * Motion primitives shared by every scene.
 *
 * Timing is always expressed in seconds and converted with the composition fps,
 * so a scene behaves identically at 30 and 60 fps.
 */

export const easeOutExpo = (t: number): number => {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return 1 - Math.pow(2, -10 * t);
};

export const easeInOutCubic = (t: number): number => {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

export const clamp01 = (t: number): number => Math.min(1, Math.max(0, t));

/** Progress 0..1 of an element that enters at `delay` and lasts `duration`. */
export const enterProgress = (
  frame: number,
  fps: number,
  delaySeconds: number,
  durationSeconds: number,
): number => {
  const start = delaySeconds * fps;
  const length = Math.max(1, durationSeconds * fps);
  return easeOutExpo(clamp01((frame - start) / length));
};

/** Linear progress, for things that should not ease (e.g. grain drift). */
export const linearProgress = (
  frame: number,
  fps: number,
  delaySeconds: number,
  durationSeconds: number,
): number => {
  const start = delaySeconds * fps;
  return clamp01((frame - start) / Math.max(1, durationSeconds * fps));
};
