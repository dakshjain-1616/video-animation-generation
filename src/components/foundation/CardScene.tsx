import type { ReactNode } from "react";
import { useStage } from "../../lib/stage";
import type { SurfaceName } from "../../packs/types";
import { KineticHeading } from "./KineticHeading";
import { SceneShell } from "./SceneShell";

/**
 * CardScene: the house layout for the open and close cards.
 *
 * The heading is always vertically centered on the stage and the caller marks
 * one accent line. Any single drawn element (a line, dot or small icon) is
 * passed as children; nothing else belongs on a card.
 */
export const CardScene = ({
  lines,
  surface = "night",
  highlight,
  children,
}: {
  /** Heading, one array element per visual line (2-4). */
  lines: string[];
  surface?: SurfaceName;
  /** Index of the one accent line. */
  highlight?: number[];
  children?: ReactNode;
}) => {
  const stage = useStage();
  return (
    <SceneShell surface={surface}>
      <KineticHeading
        size="xl"
        lines={lines}
        x={stage.left}
        y={stage.cardY}
        highlight={highlight}
        stagger={0.12}
      />
      {children}
    </SceneShell>
  );
};
