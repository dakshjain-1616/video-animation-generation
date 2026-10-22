import type { StylePack } from "./types";

/**
 * Sunset Paper — warm peach stock, deep umber ink, a burnt coral accent.
 * Same editorial bones as editorial-ink, but a softer, sunlit register.
 */
export const sunsetPaper: StylePack = {
  id: "sunset-paper",
  palette: {
    paper: "#F3E3D3",
    ink: "#241A15",
    muted: "#7A655A",
    accent: "#C2410C",
    accentOnDark: "#FF8A5B",
    fill: "#E8D2BE",
    night: "#1A1210",
    chalk: "#F8EEE5",
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
  texture: { grain: 0.055, vignette: 0.12 },
  motion: { enter: 0.6, stagger: 0.11, hold: 1.4 },
  transitions: ["cut", "paper-dip"],
  surface: {
    paper: { bg: "#F3E3D3", fg: "#241A15", sub: "#7A655A", accent: "#C2410C" },
    night: { bg: "#1A1210", fg: "#F8EEE5", sub: "#B9A69A", accent: "#FF8A5B" },
  },
};
