import { ThemeProvider } from "../../lib/theme";
import { activePack, packForStage } from "../../packs/registry";
import { useStage } from "../../lib/stage";
import type { SurfaceName } from "../../packs/types";
import { PaperBackground } from "./PaperBackground";
import { PaperDip } from "./PaperDip";
import { AbsoluteFill } from "remotion";
import type { ReactNode } from "react";

/**
 * Common frame for every scene: style pack + surface + texture + optional
 * paper-dip entrance and exit. Scenes never set their own background.
 */
export const SceneShell = ({
  surface,
  children,
  dipIn = true,
  dipOut = true,
}: {
  surface: SurfaceName;
  children: ReactNode;
  dipIn?: boolean;
  dipOut?: boolean;
}) => {
  const { portrait } = useStage();
  const pack = packForStage(activePack(), portrait);
  return (
    <ThemeProvider pack={pack} surface={surface}>
      <AbsoluteFill style={{ fontFamily: pack.fonts.text }}>
        <PaperBackground>
          {children}
          {dipIn ? <PaperDip mode="in" duration={0.35} /> : null}
          {dipOut ? <PaperDip mode="out" duration={0.2} /> : null}
        </PaperBackground>
      </AbsoluteFill>
    </ThemeProvider>
  );
};
