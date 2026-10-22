import { z } from "zod";

/**
 * Storyboard schema — the render contract.
 *
 * A video is one storyboard JSON plus one code file the model wrote
 * (`entry` points at the generated Remotion entry that imports scene
 * components). Everything numeric here is computed by the agent, never by
 * the model: seconds are resolved and rounded to frames before render.
 */
export const surfaceSchema = z.enum(["paper", "night"]);

export const sceneSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  kind: z.enum(["open", "body", "close"]),
  surface: surfaceSchema,
  /** Scene length in seconds; frames is the exact render length. */
  seconds: z.number().min(2).max(5),
  frames: z.number().int().positive(),
  /** Asset id this scene anchors on, for caller-supplied media scenes. */
  asset: z.string().min(1).optional(),
  /** Voice-over line for this scene (only when the run has narration). */
  narration: z.string().min(1).optional(),
});

export const storyboardSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  category: z.literal("explainer"),
  /** Style pack id resolved by the entry template (old storyboards omit it). */
  pack: z.string().min(1).default("editorial-ink"),
  target: z.number().min(20).max(60),
  fps: z.literal(30),
  width: z.number().int(),
  height: z.number().int(),
  /** Repo-relative path to the generated Remotion entry for this project. */
  entry: z.string().min(1),
  scenes: z.array(sceneSchema).min(1),
});

export type SurfaceName = z.infer<typeof surfaceSchema>;
export type SceneSpec = z.infer<typeof sceneSchema>;
export type Storyboard = z.infer<typeof storyboardSchema>;

export const DURATION_TOLERANCE = 2.0;
export const PLATFORM_MIN = 20;
export const PLATFORM_MAX = 60;

/** Total storyboard duration in seconds. */
export function storyboardSeconds(storyboard: Storyboard): number {
  return storyboard.scenes.reduce((sum, scene) => sum + scene.seconds, 0);
}

/** Total storyboard duration in frames — the exact composition length. */
export function storyboardFrames(storyboard: Storyboard): number {
  return storyboard.scenes.reduce((sum, scene) => sum + scene.frames, 0);
}

/** Allowed window for a target length: [max(20, T-2), min(60, T+2)]. */
export function allowedWindow(target: number): { min: number; max: number } {
  return {
    min: Math.max(PLATFORM_MIN, target - DURATION_TOLERANCE),
    max: Math.min(PLATFORM_MAX, target + DURATION_TOLERANCE),
  };
}

/**
 * Hard gate from the plan: |actual - target| <= 2 s AND the result stays inside
 * the platform bounds. A great video outside this window is not done.
 */
export function durationPass(actual: number, target: number): boolean {
  const window = allowedWindow(target);
  return actual >= window.min && actual <= window.max && Math.abs(actual - target) <= DURATION_TOLERANCE;
}

/** Structural checks that can fail before any frame is rendered. */
export function storyboardIssues(storyboard: Storyboard): string[] {
  const issues: string[] = [];
  const scenes = storyboard.scenes;

  scenes.forEach((scene, i) => {
    if (scene.seconds < 2 || scene.seconds > 5) {
      issues.push(`${scene.id}: duration ${scene.seconds}s outside 2.0-5.0s`);
    }
    if (i > 0 && scenes[i - 1].surface === "night" && scene.surface === "night") {
      issues.push(`${scene.id}: two night surfaces back to back`);
    }
    if (i === 0 && scene.kind !== "open") {
      issues.push(`${scene.id}: first scene must be kind "open"`);
    }
    if (i === scenes.length - 1 && scene.kind !== "close") {
      issues.push(`${scene.id}: last scene must be kind "close"`);
    }
  });

  const ids = new Set<string>();
  for (const scene of scenes) {
    if (ids.has(scene.id)) issues.push(`${scene.id}: duplicate scene id`);
    ids.add(scene.id);
  }

  const seconds = storyboardSeconds(storyboard);
  if (!durationPass(seconds, storyboard.target)) {
    issues.push(
      `storyboard totals ${seconds.toFixed(2)}s, outside tolerance for target ${storyboard.target}s`,
    );
  }

  return issues;
}
