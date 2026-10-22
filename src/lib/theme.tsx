import { createContext, useContext, type ReactNode } from "react";
import type { StylePack, SurfaceName } from "../packs/types";

export type Theme = {
  pack: StylePack;
  surface: SurfaceName;
  /** Resolved colors for the active surface. */
  colors: StylePack["surface"][SurfaceName];
};

const ThemeContext = createContext<Theme | null>(null);

export const ThemeProvider = ({
  pack,
  surface,
  children,
}: {
  pack: StylePack;
  surface: SurfaceName;
  children: ReactNode;
}) => {
  return (
    <ThemeContext.Provider value={{ pack, surface, colors: pack.surface[surface] }}>
      {children}
    </ThemeContext.Provider>
  );
};

export function useTheme(): Theme {
  const theme = useContext(ThemeContext);
  if (!theme) {
    throw new Error("useTheme must be used inside <ThemeProvider>");
  }
  return theme;
}

/**
 * Accept a color prop written as either a token name ("ink", "accent", ...)
 * or a raw CSS value. Models reliably reach for token names, so primitives
 * resolve them deterministically instead of trusting the model to write hex.
 */
const TOKEN_ALIASES: Record<string, keyof Theme["colors"]> = {
  ink: "fg",
  fg: "fg",
  text: "fg",
  muted: "sub",
  sub: "sub",
  gray: "sub",
  accent: "accent",
  highlight: "accent",
  accentondark: "accent",
  paper: "bg",
  bg: "bg",
  night: "bg",
  background: "bg",
};

export function resolveColor(
  input: string | undefined,
  colors: Theme["colors"],
  fallback: string | undefined,
): string | undefined {
  if (!input) {
    return fallback;
  }
  const alias = TOKEN_ALIASES[input.toLowerCase().replace(/[^a-z]/g, "")];
  return alias ? colors[alias] : input;
}
