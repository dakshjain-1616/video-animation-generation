import type { StylePack } from "./types";

/**
 * Editorial Ink v1 — derived from the reference recording.
 *
 * Warm paper, near-black ink, one burnt-orange accent, heavy grotesque display
 * type, wide-tracked mono micro-labels, uniform hand-inked strokes, lots of air.
 */
export const editorialInk: StylePack = {
  id: "editorial-ink",
  palette: {
    paper: "#EDE8E3",
    ink: "#1A1A1A",
    muted: "#6D6A64",
    accent: "#E4572E",
    accentOnDark: "#FB6634",
    fill: "#DFD6CB",
    night: "#141312",
    chalk: "#F2EFEA",
  },
  fonts: {
    display: "Archivo Black",
    text: "Inter",
    mono: "IBM Plex Mono",
  },
  type: {
    display: { xl: 104, lg: 80, md: 64 },
    label: { lg: 28, md: 24, sm: 20 },
    body: { lg: 40, md: 32 },
  },
  stroke: { hair: 2, regular: 6, heavy: 10 },
  grid: { margin: 96, columns: 12, gutter: 24 },
  texture: { grain: 0.05, vignette: 0.14 },
  motion: { enter: 0.6, stagger: 0.1, hold: 1.4 },
  transitions: ["cut", "paper-dip"],
  surface: {
    paper: {
      bg: "#EDE8E3",
      fg: "#1A1A1A",
      sub: "#6D6A64",
      accent: "#E4572E",
    },
    night: {
      bg: "#141312",
      fg: "#F2EFEA",
      sub: "#A8A39B",
      accent: "#FB6634",
    },
  },
};
