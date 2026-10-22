import type { StylePack } from "../packs/types";

/**
 * Layout grid helpers.
 *
 * 12 columns with fixed margins. Everything sits on the grid, which is what
 * keeps 20-60 s videos from drifting into ad-hoc placements.
 */

export type Rect = { x: number; y: number; width: number; height: number };

export type Grid = {
  frame: { width: number; height: number };
  content: Rect;
  columnWidth: number;
  /** X coordinate of a column's left edge (1-indexed). */
  columnX: (column: number) => number;
  /** Width of `span` columns including inner gutters. */
  columnSpan: (span: number) => number;
  /** A rect covering `span` columns starting at `column`. */
  cell: (column: number, span: number, y: number, height: number) => Rect;
};

export function makeGrid(pack: StylePack, width: number, height: number): Grid {
  const { margin, columns, gutter } = pack.grid;
  const contentWidth = width - margin * 2;
  const columnWidth = (contentWidth - gutter * (columns - 1)) / columns;
  const columnX = (column: number) => margin + (column - 1) * (columnWidth + gutter);
  const columnSpan = (span: number) => span * columnWidth + (span - 1) * gutter;
  const content = { x: margin, y: margin, width: contentWidth, height: height - margin * 2 };

  return {
    frame: { width, height },
    content,
    columnWidth,
    columnX,
    columnSpan,
    cell: (column, span, y, cellHeight) => ({
      x: columnX(column),
      y,
      width: columnSpan(span),
      height: cellHeight,
    }),
  };
}

export function overlaps(a: Rect, b: Rect, padding = 0): boolean {
  return !(
    a.x + a.width + padding <= b.x ||
    b.x + b.width + padding <= a.x ||
    a.y + a.height + padding <= b.y ||
    b.y + b.height + padding <= a.y
  );
}

export function contains(outer: Rect, inner: Rect, tolerance = 0.5): boolean {
  return (
    inner.x >= outer.x - tolerance &&
    inner.y >= outer.y - tolerance &&
    inner.x + inner.width <= outer.x + outer.width + tolerance &&
    inner.y + inner.height <= outer.y + outer.height + tolerance
  );
}

/**
 * Conservative text width estimate, used for pre-render collision checks.
 * Deliberately over-estimates: a false positive costs a layout tweak, a false
 * negative ships clipped text.
 */
export function estimateTextWidth(
  text: string,
  fontSize: number,
  trackingEm: number,
  kind: "display" | "mono" | "text",
): number {
  const perChar = kind === "display" ? 0.68 : kind === "mono" ? 0.62 : 0.56;
  return text.length * (fontSize * perChar + trackingEm * fontSize);
}
