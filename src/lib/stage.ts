import { useVideoConfig } from "remotion";

/**
 * The stage: where content may sit in the current format.
 *
 * Scenes read this instead of hardcoding 1920x1080 coordinates, so one scene
 * description works in both 16:9 and 9:16. Unlike useTheme() it needs no
 * provider, so it is safe to call in a top-level scene component.
 *
 * Portrait keeps clear of the Shorts UI: the title/search bar on top and the
 * caption, buttons and progress bar at the bottom and right edge.
 */
export type Stage = {
  width: number;
  height: number;
  portrait: boolean;
  /** Safe content box: nothing meaningful is drawn outside it. */
  left: number;
  right: number;
  top: number;
  bottom: number;
  /** Where a body scene's visual lives: below the house header, filling the rest. */
  visual: { x: number; y: number; width: number; height: number };
  /** Top of a centered 3-line card heading (open and close scenes). */
  cardY: number;
  /** Safe box size and center. */
  safeWidth: number;
  safeHeight: number;
  cx: number;
  cy: number;
};

export function makeStage(width: number, height: number): Stage {
  const portrait = height > width;
  const left = portrait ? 72 : 96;
  const right = width - (portrait ? 72 : 96);
  const top = portrait ? 180 : 96;
  const bottom = height - (portrait ? 340 : 96);
  const visualTop = top + (portrait ? 230 : 190);
  return {
    visual: { x: left, y: visualTop, width: right - left, height: bottom - visualTop },
    cardY: (top + bottom) / 2 - (portrait ? 190 : 140),
    width,
    height,
    portrait,
    left,
    right,
    top,
    bottom,
    safeWidth: right - left,
    safeHeight: bottom - top,
    cx: (left + right) / 2,
    cy: (top + bottom) / 2,
  };
}

export function useStage(): Stage {
  const { width, height } = useVideoConfig();
  return makeStage(width, height);
}
