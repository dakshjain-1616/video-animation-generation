import type { StylePack } from "./types";

/**
 * Forest Ink — pale sage paper, dark green-black ink, a deep evergreen accent.
 * A quieter, more organic register for nature, health and long-form topics.
 */
export const forestInk: StylePack = {
  id: "forest-ink",
  palette: {
    paper: "#E4EBE1",
    ink: "#17241A",
    muted: "#5C6E60",
    accent: "#2F6F4E",
    accentOnDark: "#7FC49A",
    fill: "#D3DFCE",
    night: "#0F1712",
    chalk: "#EDF4EA",
  },
  fonts: {
    display: "Archivo Black",
    text: "Inter",
    mono: "IBM Plex Mono",
  },
  type: {
    display: { xl: 100, lg: 78, md: 62 },
    label: { lg: 27, md: 23, sm: 19 },
    body: { lg: 39, md: 31 },
  },
  stroke: { hair: 2, regular: 5, heavy: 9 },
  grid: { margin: 92, columns: 12, gutter: 22 },
  texture: { grain: 0.045, vignette: 0.11 },
  motion: { enter: 0.55, stagger: 0.09, hold: 1.3 },
  transitions: ["cut", "paper-dip"],
  surface: {
    paper: { bg: "#E4EBE1", fg: "#17241A", sub: "#5C6E60", accent: "#2F6F4E" },
    night: { bg: "#0F1712", fg: "#EDF4EA", sub: "#9DAD9F", accent: "#7FC49A" },
  },
};
