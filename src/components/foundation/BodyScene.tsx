import type { ReactNode } from "react";
import { useStage } from "../../lib/stage";
import type { SurfaceName } from "../../packs/types";
import { KineticHeading } from "./KineticHeading";
import { SceneShell } from "./SceneShell";
import { SectionHeader } from "./SectionHeader";

/**
 * BodyScene: the house layout for an explainer body scene.
 *
 * The wrapper owns the chapter header and the heading anchor, so every body
 * scene starts at the same place regardless of what the model draws below it.
 * Scenes pass their visual as children and keep using stage.visual for layout.
 */
export const BodyScene = ({
  index,
  kicker,
  lines,
  surface = "paper",
  children,
}: {
  /** Chapter number shown in the header, e.g. "02". */
  index: string;
  /** Short mono chapter label, e.g. "SOUND". */
  kicker: string;
  /** Display heading, one array element per visual line (max 2). */
  lines: string[];
  surface?: SurfaceName;
  children: ReactNode;
}) => {
  const stage = useStage();
  return (
    <SceneShell surface={surface}>
      <SectionHeader index={index} title={kicker} x={stage.left} y={stage.top} />
      <KineticHeading size="md" lines={lines} x={stage.left} y={stage.top + 56} />
      {children}
    </SceneShell>
  );
};
