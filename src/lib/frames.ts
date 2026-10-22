/**
 * Frame allocation with cumulative rounding, so per-scene frame counts always
 * sum to the composition's exact frame count (no drift from independent rounds).
 */
export function allocateFrames(durations: number[], fps: number): number[] {
  let elapsed = 0;
  let previous = 0;

  return durations.map((duration) => {
    elapsed += duration;
    const cumulative = Math.round(elapsed * fps);
    const frames = cumulative - previous;
    previous = cumulative;
    return frames;
  });
}
