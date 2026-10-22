import type { StylePack } from "./types";
import { editorialInk } from "./editorial-ink";
import { clinicalSlate } from "./clinical-slate";
import { forestInk } from "./forest-ink";
import { monoGraphite } from "./mono-graphite";
import { sunsetPaper } from "./sunset-paper";

/**
 * The pack registry. Adding a style pack is one file next to the others plus a
 * line here (and one in vga/pipeline.py, which validates the CLI choice).
 */
export const packs: Record<string, StylePack> = {
  "editorial-ink": editorialInk,
  "clinical-slate": clinicalSlate,
  "sunset-paper": sunsetPaper,
  "forest-ink": forestInk,
  "mono-graphite": monoGraphite,
};

/**
 * The active pack for the current bundle. Each generated project is its own
 * single-composition bundle, so a module-level selection set once by the
 * deterministic entry template is unambiguous.
 */
let active: StylePack = editorialInk;

export const setActivePack = (id: string): void => {
  const pack = packs[id];
  if (!pack) {
    throw new Error(`unknown style pack: "${id}" (have: ${Object.keys(packs).join(", ")})`);
  }
  active = pack;
};

export const activePack = (): StylePack => active;

/**
 * Phone screens show a 1080px-wide frame at roughly a third of its size, so
 * labels and body copy get a larger scale in portrait. Display type is fitted
 * to the stage by KineticHeading instead.
 */
const PORTRAIT_TEXT_SCALE = 1.4;

export const packForStage = (pack: StylePack, portrait: boolean): StylePack => {
  if (!portrait) return pack;
  const grow = (sizes: Record<string, number>) =>
    Object.fromEntries(Object.entries(sizes).map(([key, size]) => [key, Math.round(size * PORTRAIT_TEXT_SCALE)]));
  return {
    ...pack,
    type: {
      ...pack.type,
      label: grow(pack.type.label) as StylePack["type"]["label"],
      body: grow(pack.type.body) as StylePack["type"]["body"],
    },
  };
};
