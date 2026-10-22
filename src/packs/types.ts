/**
 * Style pack contract.
 *
 * A style pack is the single source of truth for how a render looks: palette,
 * type scale, stroke weights, grid, texture and motion. Scenes never hardcode
 * colors or sizes; they read these tokens so the whole video stays consistent.
 */

export type Palette = {
  paper: string;
  ink: string;
  muted: string;
  accent: string;
  accentOnDark: string;
  fill: string;
  /** Background for dark "inverted" scenes. */
  night: string;
  /** Ink color used on top of `night`. */
  chalk: string;
};

export type FontFamilies = {
  display: string;
  text: string;
  mono: string;
};

export type TypeScale = {
  display: { xl: number; lg: number; md: number };
  label: { lg: number; md: number; sm: number };
  body: { lg: number; md: number };
};

export type StylePack = {
  id: string;
  palette: Palette;
  fonts: FontFamilies;
  type: TypeScale;
  stroke: { hair: number; regular: number; heavy: number };
  grid: { margin: number; columns: number; gutter: number };
  texture: { grain: number; vignette: number };
  motion: { enter: number; stagger: number; hold: number };
  transitions: Array<"cut" | "paper-dip">;
  /** Surface variants a scene can request. */
  surface: {
    paper: { bg: string; fg: string; sub: string; accent: string };
    night: { bg: string; fg: string; sub: string; accent: string };
  };
};

export type SurfaceName = "paper" | "night";
