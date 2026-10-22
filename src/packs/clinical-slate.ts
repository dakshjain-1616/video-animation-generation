import type { StylePack } from "./types";

/**
 * Clinical Slate — the proof that packs are swappable. Cool grays, one deep
 * blue accent, tighter display type, lighter texture. Same fonts as
 * editorial-ink on purpose: no new dependencies, so the test is purely tokens.
 */
export const clinicalSlate: StylePack = {
  id: "clinical-slate",
  palette: {
    paper: "#E9EDF2",
    ink: "#14202E",
    muted: "#5F6B7A",
    accent: "#1D4ED8",
    accentOnDark: "#5B9DFF",
    fill: "#D7DDE5",
    night: "#0B1220",
    chalk: "#E8EDF4",
  },
  fonts: {
    display: "Archivo Black",
    text: "Inter",
    mono: "IBM Plex Mono",
  },
  type: {
    display: { xl: 92, lg: 72, md: 58 },
    label: { lg: 26, md: 22, sm: 18 },
    body: { lg: 38, md: 30 },
  },
  stroke: { hair: 2, regular: 5, heavy: 9 },
  grid: { margin: 88, columns: 12, gutter: 20 },
  texture: { grain: 0.03, vignette: 0.1 },
  motion: { enter: 0.5, stagger: 0.08, hold: 1.2 },
  transitions: ["cut", "paper-dip"],
  surface: {
    paper: {
      bg: "#E9EDF2",
      fg: "#14202E",
      sub: "#5F6B7A",
      accent: "#1D4ED8",
    },
    night: {
      bg: "#0B1220",
      fg: "#E8EDF4",
      sub: "#8C97A6",
      accent: "#5B9DFF",
    },
  },
};
