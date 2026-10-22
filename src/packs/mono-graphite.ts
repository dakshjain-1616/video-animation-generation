import type { StylePack } from "./types";

/**
 * Mono Graphite — neutral studio gray, near-black ink, a sharp crimson accent.
 * High contrast and low chroma, for technical or news-heavy subjects.
 */
export const monoGraphite: StylePack = {
  id: "mono-graphite",
  palette: {
    paper: "#EAEAEA",
    ink: "#121212",
    muted: "#666666",
    accent: "#C81E4A",
    accentOnDark: "#FF6B8A",
    fill: "#D8D8D8",
    night: "#0B0B0B",
    chalk: "#F4F4F4",
  },
  fonts: {
    display: "Archivo Black",
    text: "Inter",
    mono: "IBM Plex Mono",
  },
  type: {
    display: { xl: 102, lg: 80, md: 64 },
    label: { lg: 28, md: 24, sm: 20 },
    body: { lg: 40, md: 32 },
  },
  stroke: { hair: 2, regular: 6, heavy: 10 },
  grid: { margin: 96, columns: 12, gutter: 24 },
  texture: { grain: 0.03, vignette: 0.09 },
  motion: { enter: 0.55, stagger: 0.1, hold: 1.35 },
  transitions: ["cut", "paper-dip"],
  surface: {
    paper: { bg: "#EAEAEA", fg: "#121212", sub: "#666666", accent: "#C81E4A" },
    night: { bg: "#0B0B0B", fg: "#F4F4F4", sub: "#A6A6A6", accent: "#FF6B8A" },
  },
};
