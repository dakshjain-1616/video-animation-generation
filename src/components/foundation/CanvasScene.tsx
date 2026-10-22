import type { ReactNode } from "react";
import type { SurfaceName } from "../../packs/types";
import { SceneShell } from "./SceneShell";

/** Theme and deterministic transitions, leaving composition to the scene. */
export const CanvasScene = ({ surface = "paper", children }: {
  surface?: SurfaceName;
  children: ReactNode;
}) => <SceneShell surface={surface}>{children}</SceneShell>;
